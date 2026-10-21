"""
02_fetch.py: Stage 2 - Fetch cropped Sentinel-1 VV/VH GeoTIFFs via Sentinel Hub Process API in metric UTM CRS.
Uses atomic file writing, retries, and dimension-capping.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple

import requests
from pipeline_utils import (
    load_config,
    get_cdse_token,
    get_utm_bounds,
    calculate_grid_size,
    PROCESS_URL,
)

EVALSCRIPT = """
//VERSION=3
function setup() {
    return {
        input: [{
            bands: ["VV", "VH"],
            units: "LINEAR_POWER"
        }],
        output: {
            id: "default",
            bands: 2,
            sampleType: "FLOAT32"
        }
    };
}

function evaluatePixel(sample) {
    return [sample.VV, sample.VH];
}
"""

VALID_TIFF_SIGNATURES = (
    b"II*\x00",
    b"MM\x00*",
    b"II+\x00",
    b"MM\x00+",
)


def fetch_geotiff(
    token: str,
    utm_bounds: Tuple[float, float, float, float],
    utm_epsg: int,
    width_px: int,
    height_px: int,
    scene_datetime_iso: str,
    orbit_direction: str,
    output_path: Path,
    max_retries: int = 3,
) -> None:
    """Download single Sentinel-1 VV/VH GeoTIFF in UTM projection with atomic write and retries."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(output_path.stem + ".part.tif")

    dt = datetime.fromisoformat(scene_datetime_iso.replace("Z", "+00:00"))
    from_iso = (dt - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_iso = (dt + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")

    min_x, min_y, max_x, max_y = utm_bounds

    request_body = {
        "input": {
            "bounds": {
                "bbox": [min_x, min_y, max_x, max_y],
                "properties": {
                    "crs": f"http://www.opengis.net/def/crs/EPSG/0/{utm_epsg}"
                },
            },
            "data": [
                {
                    "type": "sentinel-1-grd",
                    "dataFilter": {
                        "timeRange": {
                            "from": from_iso,
                            "to": to_iso,
                        },
                        "acquisitionMode": "IW",
                        "polarization": "DV",
                        "resolution": "HIGH",
                        "orbitDirection": orbit_direction.upper(),
                    },
                    "processing": {
                        "backCoeff": "SIGMA0_ELLIPSOID",
                        "orthorectify": True,
                        "demInstance": "COPERNICUS_30",
                        "speckleFilter": {
                            "type": "LEE",
                            "windowSizeX": 3,
                            "windowSizeY": 3,
                        },
                    },
                }
            ],
        },
        "output": {
            "width": width_px,
            "height": height_px,
            "responses": [
                {
                    "identifier": "default",
                    "format": {"type": "image/tiff"},
                }
            ],
        },
        "evalscript": EVALSCRIPT,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "image/tiff",
    }

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            print(f"  Requesting Process API (Attempt {attempt}/{max_retries})...")
            response = requests.post(
                PROCESS_URL,
                json=request_body,
                headers=headers,
                timeout=300,
            )

            if response.status_code != 200:
                raise RuntimeError(
                    f"Process API error {response.status_code}: {response.text[:500]}"
                )

            content_type = response.headers.get("Content-Type", "")
            if "image/tiff" not in content_type.lower():
                raise RuntimeError(f"Expected TIFF, got {content_type}: {response.text[:200]}")

            if len(response.content) < 500:
                raise RuntimeError(f"Unexpectedly small response: {len(response.content)} bytes")

            # Check TIFF magic signature
            if response.content[:4] not in VALID_TIFF_SIGNATURES:
                raise RuntimeError("Response content lacks valid GeoTIFF header magic bytes.")

            # Write atomically
            temp_path.write_bytes(response.content)
            temp_path.replace(output_path)
            print(f"  -> Successfully saved: {output_path.name} ({output_path.stat().st_size / 1_000_000:.2f} MB)")
            return

        except Exception as exc:
            last_err = exc
            print(f"  Attempt {attempt} failed: {exc}")
            if temp_path.exists():
                temp_path.unlink()
            if attempt < max_retries:
                wait_s = 2 ** attempt
                print(f"  Retrying in {wait_s}s...")
                time.sleep(wait_s)

    raise RuntimeError(f"Failed to fetch GeoTIFF after {max_retries} attempts: {last_err}")


def main():
    parser = argparse.ArgumentParser(description="Fetch Sentinel-1 GeoTIFFs in Metric UTM Grid")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--force", action="store_true", help="Force re-download even if files exist")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_dir = Path(cfg["run_dir"])
    metadata_file = run_dir / "metadata.json"

    if not metadata_file.exists():
        sys.exit(f"ERROR: {metadata_file} not found. Please run Stage 1 (01_catalog.py) first.")

    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    catalog_info = metadata.get("stage_1_catalog", {})
    selected_pair = catalog_info.get("selected_pair")

    if not selected_pair:
        sys.exit("ERROR: No selected candidate pair found in metadata.json. Run 01_catalog.py first.")

    token = get_cdse_token()

    utm_epsg = cfg["utm_epsg"]
    utm_bounds = get_utm_bounds(cfg["bbox"], utm_epsg)
    width_px, height_px, eff_res = calculate_grid_size(utm_bounds, cfg["resolution_m"])

    print("=" * 70)
    print("STAGE 2: SENTINEL HUB PROCESS API GEOTIFF DOWNLOAD")
    print("=" * 70)
    print(f"Run:             {cfg['name']} ({cfg['event_date']})")
    print(f"Target CRS:      EPSG:{utm_epsg} (UTM Metric)")
    print(f"UTM Bounds:      min_x={utm_bounds[0]}, min_y={utm_bounds[1]}, max_x={utm_bounds[2]}, max_y={utm_bounds[3]}")
    print(f"Requested Res:   {cfg['resolution_m']} m (Effective: {eff_res} m)")
    print(f"Grid Dimensions: {width_px} x {height_px} pixels")
    print(f"Relative Orbit:  {selected_pair['relative_orbit']} ({selected_pair['orbit_direction']})")

    pre_scene = selected_pair["pre_scene"]
    post_scene = selected_pair["post_scene"]

    pre_date_str = pre_scene["datetime"][:10]
    post_date_str = post_scene["datetime"][:10]

    data_dir = Path(cfg["data_dir"])
    pre_path = data_dir / f"pre_{pre_date_str}.tif"
    post_path = data_dir / f"post_{post_date_str}.tif"

    print(f"\n[1/2] PRE-EVENT ACQUISITION: {pre_scene['datetime']}")
    if pre_path.exists() and not args.force:
        print(f"  Existing file found: {pre_path} (Skipping download, use --force to overwrite)")
    else:
        fetch_geotiff(
            token=token,
            utm_bounds=utm_bounds,
            utm_epsg=utm_epsg,
            width_px=width_px,
            height_px=height_px,
            scene_datetime_iso=pre_scene["datetime"],
            orbit_direction=selected_pair["orbit_direction"],
            output_path=pre_path,
        )

    print(f"\n[2/2] POST-EVENT ACQUISITION: {post_scene['datetime']}")
    if post_path.exists() and not args.force:
        print(f"  Existing file found: {post_path} (Skipping download, use --force to overwrite)")
    else:
        fetch_geotiff(
            token=token,
            utm_bounds=utm_bounds,
            utm_epsg=utm_epsg,
            width_px=width_px,
            height_px=height_px,
            scene_datetime_iso=post_scene["datetime"],
            orbit_direction=selected_pair["orbit_direction"],
            output_path=post_path,
        )

    # Update metadata
    metadata["stage_2_fetch"] = {
        "status": "COMPLETED",
        "utm_epsg": utm_epsg,
        "utm_bounds": utm_bounds,
        "width_px": width_px,
        "height_px": height_px,
        "effective_resolution_m": eff_res,
        "pre_file": str(pre_path),
        "post_file": str(post_path),
    }
    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"\nStage 2 completed. Metadata updated: {metadata_file}")


if __name__ == "__main__":
    main()
