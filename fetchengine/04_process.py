"""
04_process.py: Stage 4 - Sentinel-1 radiometric processing, change detection, and vectorization.
Converts linear power to dB, isolates surface changes (inundation), excludes permanent water,
filters minimum area, and exports candidates.geojson and change_mask.tif.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, Tuple

import numpy as np
import rasterio
import rasterio.features
from rasterio.warp import transform_geom
from shapely.geometry import shape

from pipeline_utils import load_config


def linear_to_db(power_array: np.ndarray) -> np.ndarray:
    """Convert linear power backscatter to decibels (dB), preserving masks and NaNs."""
    db = np.full(power_array.shape, np.nan, dtype=np.float32)
    valid = np.isfinite(power_array) & (power_array > 0)
    db[valid] = 10.0 * np.log10(power_array[valid])
    return db


def compute_otsu_threshold(values: np.ndarray, nbins: int = 256) -> float:
    """Compute Otsu threshold on a 1D numpy array."""
    valid_vals = values[np.isfinite(values)]
    if valid_vals.size == 0:
        return -3.0

    counts, bin_edges = np.histogram(valid_vals, bins=nbins)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0

    total = counts.sum()
    if total == 0:
        return -3.0

    weight1 = np.cumsum(counts)
    weight2 = np.cumsum(counts[::-1])[::-1]

    # Prevent division by zero
    valid_split = (weight1[:-1] > 0) & (weight2[1:] > 0)
    if not np.any(valid_split):
        return float(np.median(valid_vals))

    cumsum_centers = np.cumsum(counts * bin_centers)
    mean1 = cumsum_centers[:-1] / np.maximum(weight1[:-1], 1)

    cumsum_rev = np.cumsum((counts * bin_centers)[::-1])[::-1]
    mean2 = cumsum_rev[1:] / np.maximum(weight2[1:], 1)

    variance = weight1[:-1] * weight2[1:] * ((mean1 - mean2) ** 2)
    best_idx = np.argmax(variance)
    return float(bin_centers[best_idx])


def main():
    parser = argparse.ArgumentParser(description="Process Sentinel-1 Change Features & Detect Inundation Candidates")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--threshold", type=float, default=None, help="Explicit ΔVV dB threshold override (e.g. -3.0)")
    parser.add_argument("--force", action="store_true", help="Force reprocessing even if output exists")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_dir = Path(cfg["run_dir"])
    metadata_file = run_dir / "metadata.json"

    if not metadata_file.exists():
        sys.exit(f"ERROR: {metadata_file} not found. Run Stages 1-3 first.")

    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    fetch_info = metadata.get("stage_2_fetch", {})
    pre_path = Path(fetch_info.get("pre_file", ""))
    post_path = Path(fetch_info.get("post_file", ""))

    change_mask_path = run_dir / "change_mask.tif"
    candidates_geojson_path = run_dir / "candidates.geojson"

    if change_mask_path.exists() and candidates_geojson_path.exists() and not args.force:
        print(f"Stage 4 outputs already exist in {run_dir}. Use --force to reprocess.")
        return

    print("=" * 70)
    print("STAGE 4: CHANGE DETECTION, THRESHOLDING & VECTORIZATION")
    print("=" * 70)

    # Read pre and post rasters
    with rasterio.open(pre_path) as pre_src, rasterio.open(post_path) as post_src:
        meta = pre_src.meta.copy()
        transform = pre_src.transform
        utm_crs = str(pre_src.crs)

        pre_vv_raw = pre_src.read(1, masked=True)
        pre_vh_raw = pre_src.read(2, masked=True)
        post_vv_raw = post_src.read(1, masked=True)
        post_vh_raw = post_src.read(2, masked=True)

    # Convert linear power to dB
    pre_vv_db = linear_to_db(pre_vv_raw.filled(np.nan))
    pre_vh_db = linear_to_db(pre_vh_raw.filled(np.nan))
    post_vv_db = linear_to_db(post_vv_raw.filled(np.nan))
    post_vh_db = linear_to_db(post_vh_raw.filled(np.nan))

    valid_mask = (
        np.isfinite(pre_vv_db)
        & np.isfinite(pre_vh_db)
        & np.isfinite(post_vv_db)
        & np.isfinite(post_vh_db)
    )

    # Compute differential features
    delta_vv = np.full(pre_vv_db.shape, np.nan, dtype=np.float32)
    delta_vh = np.full(pre_vh_db.shape, np.nan, dtype=np.float32)
    delta_vv[valid_mask] = post_vv_db[valid_mask] - pre_vv_db[valid_mask]
    delta_vh[valid_mask] = post_vh_db[valid_mask] - pre_vh_db[valid_mask]

    # Exclude permanent water (water present before the event)
    # Open water typically exhibits VV < -16 dB and VH < -23 dB
    permanent_water = valid_mask & (pre_vv_db < -16.0) & (pre_vh_db < -23.0)
    n_perm_water = int(permanent_water.sum())
    print(f"Permanent water pixels excluded: {n_perm_water:,} ({n_perm_water / valid_mask.sum() * 100:.2f}% of valid)")

    # Candidate pixels eligible for flood change (valid, not permanent water, negative delta)
    eligible = valid_mask & (~permanent_water)
    eligible_deltas = delta_vv[eligible]

    # Determine threshold
    method = cfg.get("threshold_method", "adaptive_std")
    k_std = float(cfg.get("k_std", 1.5))

    if args.threshold is not None:
        threshold = float(args.threshold)
        method_desc = f"Manual override: {threshold:.2f} dB"
    elif method == "otsu":
        # Otsu on eligible negative drops
        neg_deltas = eligible_deltas[eligible_deltas < 0]
        threshold = compute_otsu_threshold(neg_deltas)
        # Clamp to realistic physical range [-6.0, -2.0]
        threshold = float(np.clip(threshold, -6.0, -2.0))
        method_desc = f"Otsu threshold on negative backscatter: {threshold:.2f} dB"
    else:
        # Adaptive std: mean - k * std
        mean_d = float(np.mean(eligible_deltas))
        std_d = float(np.std(eligible_deltas))
        threshold = mean_d - (k_std * std_d)
        # Clamp to realistic physical range [-6.0, -2.0]
        threshold = float(np.clip(threshold, -6.0, -2.0))
        method_desc = f"Adaptive (mean - {k_std}*std) clamped: {threshold:.2f} dB (mean={mean_d:.2f}, std={std_d:.2f})"

    print(f"Thresholding Method: {method_desc}")
    print(f"Selected Inundation Threshold: {threshold:.2f} dB")

    # Raw candidate change mask (1 = candidate inundation, 0 = no change, 255 = nodata)
    raw_mask = (delta_vv < threshold) & eligible

    # Save change_mask.tif
    meta.update({
        "count": 1,
        "dtype": "uint8",
        "nodata": 255,
        "compress": "deflate",
    })

    out_raster_arr = np.full(raw_mask.shape, 255, dtype=np.uint8)
    out_raster_arr[valid_mask] = 0
    out_raster_arr[raw_mask] = 1

    with rasterio.open(change_mask_path, "w", **meta) as dst:
        dst.write(out_raster_arr, 1)

    print(f"\nSaved change raster: {change_mask_path.name}")

    # Vectorize candidate regions
    min_area_m2 = float(cfg.get("min_area_m2", 2000.0))
    shapes_gen = rasterio.features.shapes(
        out_raster_arr,
        mask=(out_raster_arr == 1),
        transform=transform,
    )

    features = []
    poly_idx = 1
    total_area_m2 = 0.0

    for geom, val in shapes_gen:
        if val != 1:
            continue
        try:
            poly = shape(geom)
            area_m2 = poly.area
            if area_m2 < min_area_m2:
                continue

            total_area_m2 += area_m2

            # Transform geometry to EPSG:4326 for standard GeoJSON
            geom_4326 = transform_geom(utm_crs, "EPSG:4326", geom)
            poly_4326 = shape(geom_4326)
            centroid = poly_4326.centroid

            features.append({
                "type": "Feature",
                "geometry": geom_4326,
                "properties": {
                    "id": f"cand_{poly_idx:04d}",
                    "area_m2": round(area_m2, 1),
                    "area_ha": round(area_m2 / 10000.0, 2),
                    "area_km2": round(area_m2 / 1_000_000.0, 4),
                    "threshold_db": round(threshold, 2),
                    "centroid_lon": round(centroid.x, 6),
                    "centroid_lat": round(centroid.y, 6),
                },
            })
            poly_idx += 1
        except Exception:
            continue

    # Sort candidate features by area descending
    features.sort(key=lambda f: f["properties"]["area_m2"], reverse=True)
    # Re-index
    for idx, f in enumerate(features, start=1):
        f["properties"]["id"] = f"cand_{idx:04d}"

    geojson_data = {
        "type": "FeatureCollection",
        "name": f"sentinel1_candidates_{cfg['name']}",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
        },
        "features": features,
    }

    candidates_geojson_path.write_text(json.dumps(geojson_data, indent=2), encoding="utf-8")
    print(f"Saved candidate vector polygons: {candidates_geojson_path.name}")
    print(f"Total candidate polygons: {len(features):,}")
    print(f"Total detected flood area: {total_area_m2 / 10000.0:,.1f} ha ({total_area_m2 / 1_000_000.0:,.2f} km²)")

    # Update metadata
    metadata["stage_4_process"] = {
        "status": "COMPLETED",
        "change_mask_file": str(change_mask_path),
        "candidates_geojson": str(candidates_geojson_path),
        "threshold_db": round(threshold, 2),
        "threshold_method": method_desc,
        "permanent_water_pixels": n_perm_water,
        "candidate_polygon_count": len(features),
        "total_candidate_area_ha": round(total_area_m2 / 10000.0, 2),
        "total_candidate_area_km2": round(total_area_m2 / 1_000_000.0, 4),
    }

    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"\nStage 4 completed. Metadata updated: {metadata_file}")


if __name__ == "__main__":
    main()
