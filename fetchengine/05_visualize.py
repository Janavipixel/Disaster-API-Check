"""
05_visualize.py: Stage 5 - Generate professional diagnostic previews and change maps.
Outputs: pre/post VV dB, ΔdB diverging map, mask overlay, histogram with threshold, and 2x2 summary panel.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import ListedColormap

from pipeline_utils import load_config


def linear_to_db(power_array: np.ndarray) -> np.ndarray:
    """Convert linear power to decibels (dB), preserving masks and NaNs."""
    db = np.full(power_array.shape, np.nan, dtype=np.float32)
    valid = np.isfinite(power_array) & (power_array > 0)
    db[valid] = 10.0 * np.log10(power_array[valid])
    return db


def main():
    parser = argparse.ArgumentParser(description="Render Diagnostic Preview Images and Summary Panel")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--force", action="store_true", help="Force re-rendering previews")
    args = parser.parse_args()

    cfg = load_config(args.config)
    run_dir = Path(cfg["run_dir"])
    previews_dir = Path(cfg["previews_dir"])
    metadata_file = run_dir / "metadata.json"

    if not metadata_file.exists():
        sys.exit(f"ERROR: {metadata_file} not found. Run Stages 1-4 first.")

    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    fetch_info = metadata.get("stage_2_fetch", {})
    process_info = metadata.get("stage_4_process", {})

    pre_path = Path(fetch_info.get("pre_file", ""))
    post_path = Path(fetch_info.get("post_file", ""))
    mask_path = run_dir / "change_mask.tif"

    if not pre_path.exists() or not post_path.exists() or not mask_path.exists():
        sys.exit("ERROR: Required raster files missing. Run Stage 4 first.")

    print("=" * 70)
    print("STAGE 5: DIAGNOSTIC VISUALIZATION & PREVIEW GENERATION")
    print("=" * 70)
    print(f"Previews Directory: {previews_dir.resolve()}")

    # Read rasters
    with rasterio.open(pre_path) as pre_src, rasterio.open(post_path) as post_src, rasterio.open(mask_path) as mask_src:
        pre_vv_raw = pre_src.read(1, masked=True)
        post_vv_raw = post_src.read(1, masked=True)
        mask_raw = mask_src.read(1)

    pre_vv_db = linear_to_db(pre_vv_raw.filled(np.nan))
    post_vv_db = linear_to_db(post_vv_raw.filled(np.nan))

    valid = np.isfinite(pre_vv_db) & np.isfinite(post_vv_db)
    delta_vv_db = np.full(pre_vv_db.shape, np.nan, dtype=np.float32)
    delta_vv_db[valid] = post_vv_db[valid] - pre_vv_db[valid]

    # Shared grayscale stretch across pre and post
    both_valid = np.concatenate([pre_vv_db[valid], post_vv_db[valid]])
    vmin_db, vmax_db = np.nanpercentile(both_valid, [2, 98])

    selected_pair = metadata.get("stage_1_catalog", {}).get("selected_pair", {})
    pre_date = selected_pair.get("pre_scene", {}).get("datetime", "Pre-event")[:10]
    post_date = selected_pair.get("post_scene", {}).get("datetime", "Post-event")[:10]
    threshold_db = float(process_info.get("threshold_db", -3.0))

    # 1. Pre VV dB
    print("  Generating: pre_vv_db.png")
    fig, ax = plt.subplots(figsize=(8, 7), dpi=150)
    im = ax.imshow(pre_vv_db, cmap="gray", vmin=vmin_db, vmax=vmax_db)
    plt.colorbar(im, ax=ax, label="Sentinel-1 VV Backscatter (dB)", fraction=0.046, pad=0.04)
    ax.set_title(f"{cfg['name'].title()} - Pre-Event VV ({pre_date})", fontsize=12, fontweight="bold")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(previews_dir / "pre_vv_db.png")
    plt.close(fig)

    # 2. Post VV dB
    print("  Generating: post_vv_db.png")
    fig, ax = plt.subplots(figsize=(8, 7), dpi=150)
    im = ax.imshow(post_vv_db, cmap="gray", vmin=vmin_db, vmax=vmax_db)
    plt.colorbar(im, ax=ax, label="Sentinel-1 VV Backscatter (dB)", fraction=0.046, pad=0.04)
    ax.set_title(f"{cfg['name'].title()} - Post-Event VV ({post_date})", fontsize=12, fontweight="bold")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(previews_dir / "post_vv_db.png")
    plt.close(fig)

    # 3. Delta VV dB (Diverging colormap)
    print("  Generating: delta_vv_db.png")
    fig, ax = plt.subplots(figsize=(8, 7), dpi=150)
    # Diverging: negative change (drop in backscatter/water) shown in blue/cyan or coolwarm
    im = ax.imshow(delta_vv_db, cmap="RdBu", vmin=-8.0, vmax=8.0)
    cbar = plt.colorbar(im, ax=ax, label="Backscatter Change: ΔVV (dB)", fraction=0.046, pad=0.04)
    cbar.ax.axhline(threshold_db, color="yellow", linestyle="--", linewidth=1.5, label="Threshold")
    ax.set_title(f"{cfg['name'].title()} - Backscatter Difference ΔVV\n({post_date} minus {pre_date})", fontsize=12, fontweight="bold")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(previews_dir / "delta_vv_db.png")
    plt.close(fig)

    # 4. Change Mask Overlay on Post Image
    print("  Generating: change_mask_overlay.png")
    fig, ax = plt.subplots(figsize=(8, 7), dpi=150)
    ax.imshow(post_vv_db, cmap="gray", vmin=vmin_db, vmax=vmax_db)

    # Semi-transparent high-contrast cyan overlay for flooded/changed pixels
    overlay = np.zeros((*mask_raw.shape, 4), dtype=np.float32)
    overlay[mask_raw == 1] = [0.0, 0.85, 1.0, 0.75]  # Bright Cyan with 75% opacity
    ax.imshow(overlay)
    ax.set_title(
        f"{cfg['name'].title()} - Inundation Detections Overlay\n"
        f"({process_info.get('candidate_polygon_count', 0)} clusters, {process_info.get('total_candidate_area_ha', 0)} ha)",
        fontsize=12,
        fontweight="bold",
    )
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(previews_dir / "change_mask_overlay.png")
    plt.close(fig)

    # 5. Delta VV Histogram with Threshold
    print("  Generating: delta_vv_histogram.png")
    valid_deltas = delta_vv_db[valid]
    fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
    counts, bins, patches = ax.hist(
        valid_deltas,
        bins=100,
        range=(-12.0, 10.0),
        color="#4a90e2",
        alpha=0.75,
        edgecolor="black",
        linewidth=0.5,
    )
    # Color the detection zone below threshold
    for patch, bin_left in zip(patches, bins[:-1]):
        if bin_left < threshold_db:
            patch.set_facecolor("#d9534f")  # Red for inundation candidate drop

    ax.axvline(threshold_db, color="darkred", linestyle="--", linewidth=2.0, label=f"Threshold: {threshold_db:.2f} dB")
    ax.axvline(float(np.mean(valid_deltas)), color="black", linestyle=":", linewidth=1.5, label=f"Mean: {np.mean(valid_deltas):.2f} dB")

    ax.set_xlabel("Backscatter Difference ΔVV (dB)", fontsize=11)
    ax.set_ylabel("Pixel Frequency", fontsize=11)
    ax.set_title(f"{cfg['name'].title()} - ΔVV Distribution & Inundation Cutoff", fontsize=12, fontweight="bold")
    ax.legend(loc="upper right", frameon=True)
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    fig.savefig(previews_dir / "delta_vv_histogram.png")
    plt.close(fig)

    # 6. Side-by-Side 2x2 Summary Panel
    print("  Generating: summary_panel.png")
    fig, axes = plt.subplots(2, 2, figsize=(14, 12), dpi=150)

    # Panel A: Pre VV
    im0 = axes[0, 0].imshow(pre_vv_db, cmap="gray", vmin=vmin_db, vmax=vmax_db)
    plt.colorbar(im0, ax=axes[0, 0], fraction=0.046, pad=0.04, label="dB")
    axes[0, 0].set_title(f"(A) Pre-Event VV ({pre_date})", fontsize=11, fontweight="bold")
    axes[0, 0].axis("off")

    # Panel B: Post VV
    im1 = axes[0, 1].imshow(post_vv_db, cmap="gray", vmin=vmin_db, vmax=vmax_db)
    plt.colorbar(im1, ax=axes[0, 1], fraction=0.046, pad=0.04, label="dB")
    axes[0, 1].set_title(f"(B) Post-Event VV ({post_date})", fontsize=11, fontweight="bold")
    axes[0, 1].axis("off")

    # Panel C: Delta VV
    im2 = axes[1, 0].imshow(delta_vv_db, cmap="RdBu", vmin=-8.0, vmax=8.0)
    plt.colorbar(im2, ax=axes[1, 0], fraction=0.046, pad=0.04, label="ΔVV (dB)")
    axes[1, 0].set_title(f"(C) Difference ΔVV ({post_date} - {pre_date})", fontsize=11, fontweight="bold")
    axes[1, 0].axis("off")

    # Panel D: Mask Overlay
    axes[1, 1].imshow(post_vv_db, cmap="gray", vmin=vmin_db, vmax=vmax_db)
    axes[1, 1].imshow(overlay)
    axes[1, 1].set_title(
        f"(D) Inundation Candidate Detections\n"
        f"Threshold={threshold_db:.2f} dB, Area={process_info.get('total_candidate_area_ha', 0)} ha",
        fontsize=11,
        fontweight="bold",
    )
    axes[1, 1].axis("off")

    fig.suptitle(f"Sentinel-1 Disaster Intelligence Summary: {cfg['name'].title()}", fontsize=14, fontweight="bold", y=0.98)
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])
    summary_path = previews_dir / "summary_panel.png"
    fig.savefig(summary_path)
    plt.close(fig)

    # Update metadata
    metadata["stage_5_visualize"] = {
        "status": "COMPLETED",
        "previews_directory": str(previews_dir),
        "summary_panel": str(summary_path),
    }
    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"\nStage 5 completed. All previews saved to: {previews_dir}")


if __name__ == "__main__":
    main()
