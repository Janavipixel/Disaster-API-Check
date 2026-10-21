"""
03_validate.py: Stage 3 - GeoTIFF integrity and valid-pixel coverage validator.
Fails loudly if valid-data coverage is below threshold (default 90%).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, Tuple

import numpy as np
import rasterio
from pipeline_utils import load_config


def validate_single_raster(
    path: Path, expected_crs: str, min_valid_pct: float
) -> Dict[str, Any]:
    """Validate single GeoTIFF file structure, bands, values, and valid pixel coverage."""
    if not path.exists():
        raise FileNotFoundError(f"Raster file not found: {path}")

    with rasterio.open(path) as src:
        driver = src.driver
        width = src.width
        height = src.height
        count = src.count
        crs = str(src.crs)
        transform = src.transform
        bounds = tuple(src.bounds)
        dtypes = src.dtypes

        if driver != "GTiff":
            raise RuntimeError(f"{path.name}: Expected GeoTIFF format, got {driver}")

        if count != 2:
            raise RuntimeError(f"{path.name}: Expected 2 bands (VV, VH), found {count}")

        if expected_crs.upper() not in crs.upper():
            print(f"  WARNING: Expected CRS {expected_crs}, raster reports {crs}")

        band_names = ["VV", "VH"]
        band_stats = {}
        total_cells = width * height

        for b_idx, b_name in enumerate(band_names, start=1):
            data = src.read(b_idx, masked=True)
            valid_mask = ~data.mask if hasattr(data, "mask") and isinstance(data.mask, np.ndarray) else np.isfinite(data)
            valid_vals = data.compressed() if hasattr(data, "compressed") else data[valid_mask]
            valid_vals = valid_vals[np.isfinite(valid_vals)]

            n_valid = int(valid_vals.size)
            valid_pct = (n_valid / total_cells) * 100.0

            print(
                f"  [{path.name}] {b_name} Band {b_idx}: "
                f"valid={n_valid:,}/{total_cells:,} ({valid_pct:.2f}%)"
            )

            # Strict coverage check
            if valid_pct < min_valid_pct:
                raise RuntimeError(
                    f"\n{'!' * 70}\n"
                    f"CRITICAL COVERAGE FAILURE in {path.name} ({b_name}):\n"
                    f"Only {valid_pct:.2f}% pixels are valid, which is below the required {min_valid_pct:.1f}% threshold!\n"
                    f"This indicates a satellite swath coverage clipping issue for this pass.\n"
                    f"{'!' * 70}"
                )

            if n_valid == 0:
                raise RuntimeError(f"{path.name} ({b_name}): Contains zero valid pixels.")

            min_val = float(np.min(valid_vals))
            max_val = float(np.max(valid_vals))
            mean_val = float(np.mean(valid_vals))
            std_val = float(np.std(valid_vals))

            if min_val < 0:
                raise RuntimeError(
                    f"{path.name} ({b_name}): Negative linear power detected ({min_val:.5e}). "
                    "Invalid radiometry!"
                )

            if std_val == 0:
                raise RuntimeError(f"{path.name} ({b_name}): Zero variance across valid pixels.")

            band_stats[b_name] = {
                "valid_count": n_valid,
                "total_count": total_cells,
                "valid_pct": round(valid_pct, 2),
                "min": min_val,
                "max": max_val,
                "mean": mean_val,
                "std": std_val,
            }

        return {
            "file": str(path),
            "file_size_mb": round(path.stat().st_size / 1_000_000.0, 3),
            "width": width,
            "height": height,
            "count": count,
            "crs": crs,
            "transform": [float(x) for x in transform[:6]],
            "bounds": [float(x) for x in bounds],
            "band_stats": band_stats,
        }


def check_grid_alignment(pre_stats: Dict[str, Any], post_stats: Dict[str, Any]) -> None:
    """Ensure pre and post rasters share identical pixel dimensions and spatial grids."""
    pre_shape = (pre_stats["height"], pre_stats["width"])
    post_shape = (post_stats["height"], post_stats["width"])
    if pre_shape != post_shape:
        raise RuntimeError(f"Shape mismatch: Pre is {pre_shape}, Post is {post_shape}")

    if pre_stats["crs"] != post_stats["crs"]:
        raise RuntimeError(f"CRS mismatch: Pre is {pre_stats['crs']}, Post is {post_stats['crs']}")

    if pre_stats["transform"] != post_stats["transform"]:
        # Allow tiny float rounding difference
        t_diff = np.max(np.abs(np.array(pre_stats["transform"]) - np.array(post_stats["transform"])))
        if t_diff > 1e-3:
            raise RuntimeError(
                f"Affine transform mismatch: Pre={pre_stats['transform']}, Post={post_stats['transform']}"
            )


def compute_overlap_stats(pre_path: Path, post_path: Path) -> Dict[str, Any]:
    """Compute overlapping common valid pixels across pre and post rasters."""
    with rasterio.open(pre_path) as pre_src, rasterio.open(post_path) as post_src:
        pre_b1 = pre_src.read(1, masked=True)
        post_b1 = post_src.read(1, masked=True)

        pre_mask = ~pre_b1.mask if hasattr(pre_b1, "mask") and isinstance(pre_b1.mask, np.ndarray) else np.isfinite(pre_b1)
        post_mask = ~post_b1.mask if hasattr(post_b1, "mask") and isinstance(post_b1.mask, np.ndarray) else np.isfinite(post_b1)

        common_mask = pre_mask & post_mask
        n_common = int(common_mask.sum())
        total = pre_b1.size
        common_pct = (n_common / total) * 100.0

        return {
            "common_valid_pixels": n_common,
            "total_pixels": total,
            "common_valid_pct": round(common_pct, 2),
        }


def main():
    parser = argparse.ArgumentParser(description="Validate Pre/Post GeoTIFF Integrity & Grid Alignment")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_dir = Path(cfg["run_dir"])
    metadata_file = run_dir / "metadata.json"

    if not metadata_file.exists():
        sys.exit(f"ERROR: {metadata_file} not found. Run Stage 2 first.")

    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    fetch_info = metadata.get("stage_2_fetch", {})

    pre_path = Path(fetch_info.get("pre_file", ""))
    post_path = Path(fetch_info.get("post_file", ""))

    if not pre_path.exists() or not post_path.exists():
        sys.exit(f"ERROR: One or both GeoTIFFs missing:\nPre: {pre_path}\nPost: {post_path}")

    min_valid_pct = float(cfg.get("min_valid_pixel_pct", 90.0))
    expected_crs = f"EPSG:{cfg['utm_epsg']}"

    print("=" * 70)
    print("STAGE 3: RASTER VALIDATION & GRID ALIGNMENT")
    print("=" * 70)
    print(f"Pre File:        {pre_path.name}")
    print(f"Post File:       {post_path.name}")
    print(f"Expected CRS:    {expected_crs}")
    print(f"Min Valid %:     {min_valid_pct}%")

    print("\nValidating Pre-Event Raster:")
    pre_stats = validate_single_raster(pre_path, expected_crs, min_valid_pct)

    print("\nValidating Post-Event Raster:")
    post_stats = validate_single_raster(post_path, expected_crs, min_valid_pct)

    print("\nChecking Pre/Post Grid Alignment...")
    check_grid_alignment(pre_stats, post_stats)
    print("  -> Grids match perfectly (dimensions, transform, CRS).")

    overlap_stats = compute_overlap_stats(pre_path, post_path)
    print(f"  -> Common valid overlap: {overlap_stats['common_valid_pixels']:,} / {overlap_stats['total_pixels']:,} ({overlap_stats['common_valid_pct']}%)")

    # Update metadata
    metadata["stage_3_validate"] = {
        "status": "PASSED",
        "pre_stats": pre_stats,
        "post_stats": post_stats,
        "overlap_stats": overlap_stats,
    }
    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"\nStage 3 Passed! Metadata updated: {metadata_file}")


if __name__ == "__main__":
    main()
