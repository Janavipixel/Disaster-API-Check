
from pathlib import Path

import numpy as np
import rasterio
import matplotlib.pyplot as plt

DATA = Path("data")
OUT = DATA / "previews"
OUT.mkdir(parents=True, exist_ok=True)

files = {
    "pre": DATA / "pre_2026-09-22.tif",
    "post": DATA / "post_2026-10-04.tif",
}

rasters = {}
profiles = {}

# --------------------------------------------------
# 1. Read rasters and inspect valid-pixel coverage
# --------------------------------------------------
for label, path in files.items():
    if not path.exists():
        raise FileNotFoundError(f"Raster not found: {path.resolve()}")

    with rasterio.open(path) as src:
        # Read masked data so nodata and internal masks are respected.
        data = src.read(masked=True).astype(np.float32)
        arr = data.filled(np.nan)

        # Exclude non-finite values from all calculations.
        arr[~np.isfinite(arr)] = np.nan

        rasters[label] = arr
        profiles[label] = {
            "shape": (src.height, src.width),
            "transform": src.transform,
            "crs": src.crs,
            "bounds": src.bounds,
            "count": src.count,
        }

        print(f"\n{label.upper()}: {path}")
        print(f"Dimensions: {src.width} x {src.height}")
        print(f"CRS: {src.crs}")
        print(f"Bounds: {src.bounds}")
        print(f"Transform: {src.transform}")

        if src.count < 2:
            raise ValueError(f"{path} must contain VV and VH bands.")

        for b in range(src.count):
            band = arr[b]
            valid = np.isfinite(band)
            n_valid = int(valid.sum())
            total = band.size

            print(
                f"Band {b + 1}: valid={n_valid:,}/{total:,} "
                f"({100 * n_valid / total:.2f}%), "
                f"invalid={total - n_valid:,} "
                f"({100 * (total - n_valid) / total:.2f}%)"
            )

# --------------------------------------------------
# 2. Check that both rasters share the same pixel grid
# --------------------------------------------------
pre_meta = profiles["pre"]
post_meta = profiles["post"]

same_grid = (
    pre_meta["shape"] == post_meta["shape"]
    and pre_meta["transform"] == post_meta["transform"]
    and pre_meta["crs"] == post_meta["crs"]
)

print(f"\nSame pixel grid: {same_grid}")

if not same_grid:
    raise RuntimeError(
        "Rasters do not share the same grid. "
        "Align/resample them before calculating pixel-wise change."
    )

if pre_meta["count"] != post_meta["count"]:
    raise RuntimeError("Pre/post band counts do not match.")

# --------------------------------------------------
# 3. Convert linear power to decibels
# --------------------------------------------------
def to_db(power):
    result = np.full(power.shape, np.nan, dtype=np.float32)
    valid = np.isfinite(power) & (power > 0)
    result[valid] = 10.0 * np.log10(power[valid])
    return result


band_names = {0: "VV", 1: "VH"}

# --------------------------------------------------
# 4. Save pre/post VV and VH previews
# --------------------------------------------------
for label, data in rasters.items():
    for band_index, band_name in band_names.items():
        db = to_db(data[band_index])
        valid = np.isfinite(db)

        if not np.any(valid):
            print(f"Skipping {label} {band_name}: no valid pixels.")
            continue

        lo, hi = np.nanpercentile(db[valid], [2, 98])

        fig, ax = plt.subplots(figsize=(9, 7))
        image = ax.imshow(
            np.ma.masked_invalid(db),
            cmap="gray",
            vmin=lo,
            vmax=hi,
        )
        fig.colorbar(image, ax=ax, label="Backscatter (dB)")
        ax.set_title(f"{label.upper()} - {band_name}")
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(
            OUT / f"{label}_{band_name.lower()}.png",
            dpi=150,
        )
        plt.close(fig)

# --------------------------------------------------
# 5. Preliminary pixel-wise change maps
# --------------------------------------------------
common = {}

for band_index, band_name in band_names.items():
    pre_db = to_db(rasters["pre"][band_index])
    post_db = to_db(rasters["post"][band_index])

    valid = np.isfinite(pre_db) & np.isfinite(post_db)
    n_valid = int(valid.sum())
    common[band_name] = valid

    print(f"\n{band_name}: common valid pixels = {n_valid:,}")

    if n_valid == 0:
        print(f"Skipping {band_name} change: no overlapping valid pixels.")
        continue

    change = np.full(pre_db.shape, np.nan, dtype=np.float32)
    change[valid] = post_db[valid] - pre_db[valid]

    limit = float(np.nanpercentile(np.abs(change[valid]), 98))
    if not np.isfinite(limit) or limit == 0:
        limit = 1.0

    fig, ax = plt.subplots(figsize=(10, 7))
    image = ax.imshow(
        np.ma.masked_invalid(change),
        cmap="RdBu_r",
        vmin=-limit,
        vmax=limit,
    )
    fig.colorbar(
        image,
        ax=ax,
        label=f"{band_name} change (dB): post minus pre",
    )
    ax.set_title(f"Preliminary Sentinel-1 {band_name} Change")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(OUT / f"{band_name.lower()}_change.png", dpi=150)
    plt.close(fig)

    print("Change percentiles (dB):")
    print(np.nanpercentile(change[valid], [2, 25, 50, 75, 98]))

# --------------------------------------------------
# 6. Summarize shared VV/VH coverage
# --------------------------------------------------
if "VV" in common and "VH" in common:
    both = common["VV"] & common["VH"]
    total = both.size
    print(
        f"\nPixels valid in both dates and both bands: "
        f"{both.sum():,}/{total:,} "
        f"({100 * both.mean():.2f}%)"
    )

print(f"\nPreviews saved to: {OUT.resolve()}")
