
"""
Phase 1B: Download and validate Sentinel-1 VV/VH GeoTIFFs.

Copernicus Data Space Sentinel Hub Process API
Authentication: CDSE OAuth client credentials in .env

Example:
    py cdse_process.py --bbox 80.85 26.75 81.05 26.95 ^
        --pre-date 2026-09-29 --post-date 2026-10-04

Optional:
    --orbit DESCENDING
    --res 20
    --time-start 00:00:00 --time-end 23:59:59
    --out data

Output:
    data/pre_2026-09-29.tif
    data/post_2026-10-04.tif
    data/acquisition_metadata.json

Pixel values are linear sigma0 backscatter, not decibels.
"""

import argparse
import json
import math
import os
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import rasterio
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)

PROCESS_URL = "https://sh.dataspace.copernicus.eu/process/v1"

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


def get_token():
    """Authenticate using CDSE OAuth client credentials."""
    client_id = os.getenv("CDSE_CLIENT_ID")
    client_secret = os.getenv("CDSE_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            "Missing CDSE_CLIENT_ID or CDSE_CLIENT_SECRET. "
            "Check your .env file."
        )

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"CDSE authentication failed: HTTP {response.status_code}\n"
            f"{response.text[:1000]}"
        )

    token = response.json().get("access_token")

    if not token:
        raise RuntimeError("CDSE returned no access token.")

    return token


def validate_bbox(bbox):
    """Validate WGS84 bbox: west, south, east, north."""
    west, south, east, north = bbox

    if not (-180 <= west < east <= 180):
        raise ValueError("Invalid longitude bounds.")

    if not (-90 <= south < north <= 90):
        raise ValueError("Invalid latitude bounds.")


def image_size(bbox, resolution):
    """Estimate output dimensions from geographic bounds."""
    validate_bbox(bbox)

    if resolution <= 0:
        raise ValueError("Resolution must be positive.")

    west, south, east, north = bbox
    mid_lat = math.radians((south + north) / 2)

    width_m = (east - west) * 111320 * math.cos(mid_lat)
    height_m = (north - south) * 110540

    width = max(1, round(width_m / resolution))
    height = max(1, round(height_m / resolution))

    # Keep requests within a practical output-size limit.
    scale = min(1.0, 2500 / max(width, height))

    if scale < 1.0:
        print(
            "WARNING: Output dimensions capped at 2500 pixels. "
            f"Effective resolution is approximately "
            f"{resolution / scale:.1f} m."
        )

    return (
        max(1, round(width * scale)),
        max(1, round(height * scale)),
    )


def validate_raster(path, expected_width, expected_height):
    """Validate TIFF structure, dimensions, bands and pixel values."""
    with rasterio.open(path) as src:
        print(f"\nValidating: {path}")
        print(f"File size: {path.stat().st_size / 1_000_000:.3f} MB")
        print(f"Dimensions: {src.width} x {src.height}")
        print(f"Bands: {src.count}")
        print(f"CRS: {src.crs}")
        print(f"Data types: {src.dtypes}")
        print(f"Bounds: {src.bounds}")

        if src.driver != "GTiff":
            raise RuntimeError(
                f"Expected GeoTIFF, received {src.driver}."
            )

        if (src.width, src.height) != (
            expected_width, expected_height
        ):
            raise RuntimeError(
                "Raster dimensions do not match the requested output."
            )

        if src.count != 2:
            raise RuntimeError(
                f"Expected VV and VH bands; found {src.count}."
            )

        if src.crs is None:
            raise RuntimeError("Raster has no CRS.")

        band_names = ["VV", "VH"]
        band_stats = {}

        for band_num, name in enumerate(band_names, start=1):
            arr = src.read(band_num, masked=True)
            values = arr.compressed()
            values = values[np.isfinite(values)]

            if values.size == 0:
                raise RuntimeError(
                    f"{name}: raster contains no valid pixels."
                )

            minimum = float(np.min(values))
            maximum = float(np.max(values))
            stddev = float(np.std(values))

            print(
                f"{name}: valid={values.size}, "
                f"min={minimum:.7g}, max={maximum:.7g}, "
                f"std={stddev:.7g}"
            )

            if minimum < 0:
                raise RuntimeError(
                    f"{name}: negative values found in linear "
                    "backscatter. Check the output units and nodata."
                )

            if stddev == 0:
                raise RuntimeError(
                    f"{name}: all valid pixels are identical. "
                    "Investigate the acquisition and API response."
                )

            band_stats[name] = {
                "valid_pixels": int(values.size),
                "min": minimum,
                "max": maximum,
                "mean": float(np.mean(values)),
                "std": stddev,
            }

        return {
            "width": src.width,
            "height": src.height,
            "bands": src.count,
            "crs": str(src.crs),
            "bounds": list(src.bounds),
            "file_bytes": path.stat().st_size,
            "band_statistics": band_stats,
        }


def fetch(
    token,
    bbox,
    acquisition_date,
    orbit,
    resolution,
    output_path,
    time_start,
    time_end,
):
    """Request, validate and save one Sentinel-1 VV/VH GeoTIFF."""

    width, height = image_size(bbox, resolution)

    start_dt = datetime.fromisoformat(
        f"{acquisition_date}T{time_start}"
    )
    end_dt = datetime.fromisoformat(
        f"{acquisition_date}T{time_end}"
    )

    if start_dt >= end_dt:
        raise ValueError("The acquisition time range is invalid.")

    request_body = {
        "input": {
            "bounds": {
                "bbox": bbox,
                "properties": {
                    "crs": "http://www.opengis.net/def/crs/EPSG/0/4326"
                },
            },
            "data": [
                {
                    "type": "sentinel-1-grd",
                    "dataFilter": {
                        "timeRange": {
                            "from": f"{acquisition_date}T{time_start}Z",
                            "to": f"{acquisition_date}T{time_end}Z",
                        },
                        "acquisitionMode": "IW",
                        "polarization": "DV",
                        "resolution": "HIGH",
                        "orbitDirection": orbit,
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
            "width": width,
            "height": height,
            "responses": [
                {
                    "identifier": "default",
                    "format": {"type": "image/tiff"},
                }
            ],
        },
        "evalscript": EVALSCRIPT,
    }

    print(f"  Requested dimensions: {width} x {height}")
    print(f"  Date: {acquisition_date}")
    print(f"  UTC window: {time_start} - {time_end}")
    print(f"  Orbit direction: {orbit}")
    print("  Polarizations: VV, VH")

    response = requests.post(
        PROCESS_URL,
        json=request_body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "image/tiff",
        },
        timeout=300,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Process API returned HTTP {response.status_code}:\n"
            f"{response.text[:2000]}"
        )

    content_type = response.headers.get("Content-Type", "")

    if "image/tiff" not in content_type.lower():
        raise RuntimeError(
            "The API did not return a TIFF.\n"
            f"Content-Type: {content_type}\n"
            f"Response: {response.text[:1000]}"
        )

    if len(response.content) < 100:
        raise RuntimeError(
            f"Response is unexpectedly small: {len(response.content)} bytes."
        )

    # Write to a temporary TIFF and validate it before replacing output.
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = output_path.with_name(
        output_path.stem + ".part.tif"
    )

    try:
        temporary_path.write_bytes(response.content)

        with temporary_path.open("rb") as file:
            signature = file.read(4)

        valid_signatures = (
            b"II*\x00",
            b"MM\x00*",
            b"II+\x00",
            b"MM\x00+",
        )

        if signature not in valid_signatures:
            raise RuntimeError(
                "Response does not have a valid TIFF signature."
            )

        stats = validate_raster(
            temporary_path,
            expected_width=width,
            expected_height=height,
        )

        # Only replace the final file after validation succeeds.
        temporary_path.replace(output_path)

    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise

    print(
        f"\n  SAVED: {output_path}"
        f" ({output_path.stat().st_size / 1_000_000:.3f} MB)"
    )

    return {
        "requested_date": acquisition_date,
        "requested_utc_window": {
            "start": time_start,
            "end": time_end,
        },
        "orbit_direction_requested": orbit,
        "polarization_requested": ["VV", "VH"],
        "processing": {
            "backscatter": "SIGMA0_ELLIPSOID",
            "orthorectify": True,
            "dem": "COPERNICUS_30",
            "speckle_filter": "LEE 3x3",
            "output_units": "linear power",
        },
        "output_file": str(output_path),
        "raster": stats,
        "acquisition_timestamp_confirmed": False,
        "note": (
            "Requested date and filters are recorded. "
            "The exact selected acquisition timestamp and relative "
            "orbit must be confirmed independently using catalogue "
            "metadata."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Download and validate Sentinel-1 VV/VH GeoTIFFs "
            "from Copernicus Data Space."
        )
    )

    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        required=True,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
    )
    parser.add_argument("--pre-date", required=True)
    parser.add_argument("--post-date", required=True)

    parser.add_argument(
        "--orbit",
        choices=["ASCENDING", "DESCENDING"],
        default="DESCENDING",
    )
    parser.add_argument(
        "--res",
        type=float,
        default=20,
        help="Approximate output pixel size in metres (default: 20).",
    )
    parser.add_argument("--out", default="data")
    parser.add_argument("--time-start", default="00:00:00")
    parser.add_argument("--time-end", default="23:59:59")

    args = parser.parse_args()

    try:
        pre_date = date.fromisoformat(args.pre_date)
        post_date = date.fromisoformat(args.post_date)

        if pre_date >= post_date:
            raise ValueError(
                "The pre-event date must be earlier than the post-event date."
            )

        for time_value in (args.time_start, args.time_end):
            datetime.strptime(time_value, "%H:%M:%S")

        if args.time_start >= args.time_end:
            raise ValueError(
                "--time-start must be earlier than --time-end."
            )

        validate_bbox(args.bbox)
        image_size(args.bbox, args.res)

        output_dir = Path(args.out)

        print("=" * 60)
        print("SENTINEL-1 VV/VH DOWNLOAD AND VALIDATION")
        print("=" * 60)
        print(f"BBOX: {args.bbox}")
        print(f"PRE:  {args.pre_date}")
        print(f"POST: {args.post_date}")
        print(f"ORBIT: {args.orbit}")
        print(f"RESOLUTION: {args.res} m")

        print("\nAuthenticating with Copernicus Data Space...")
        token = get_token()
        print("Authentication successful.")

        metadata = {
            "bbox_wgs84": args.bbox,
            "resolution_requested_m": args.res,
            "orbit_direction_requested": args.orbit,
            "pre_event": None,
            "post_event": None,
        }

        print(f"\nPRE-EVENT: {args.pre_date}")
        metadata["pre_event"] = fetch(
            token=token,
            bbox=args.bbox,
            acquisition_date=args.pre_date,
            orbit=args.orbit,
            resolution=args.res,
            output_path=output_dir / f"pre_{args.pre_date}.tif",
            time_start=args.time_start,
            time_end=args.time_end,
        )

        print(f"\nPOST-EVENT: {args.post_date}")
        metadata["post_event"] = fetch(
            token=token,
            bbox=args.bbox,
            acquisition_date=args.post_date,
            orbit=args.orbit,
            resolution=args.res,
            output_path=output_dir / f"post_{args.post_date}.tif",
            time_start=args.time_start,
            time_end=args.time_end,
        )

        metadata_path = output_dir / "acquisition_metadata.json"
        metadata_path.write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )

        print("\n" + "=" * 60)
        print("PHASE 1B COMPLETED")
        print("=" * 60)
        print(f"Output directory: {output_dir.resolve()}")
        print(f"Metadata: {metadata_path.resolve()}")
        print("\nBoth rasters passed basic structural and pixel checks.")
        print(
            "IMPORTANT: Confirm exact acquisition timestamps and "
            "relative orbit compatibility before change detection."
        )

    except (
        requests.RequestException,
        RuntimeError,
        ValueError,
        rasterio.errors.RasterioError,
        OSError,
    ) as exc:
        sys.exit(f"\nERROR: {exc}")


if __name__ == "__main__":
    main()
