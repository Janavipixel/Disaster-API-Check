# Sentinel-1 Disaster Change-Detection Pipeline: User & Developer Guide

## 1. Project Overview

This project is an **Earth Observation (EO) and geospatial decision-support pipeline** built on synthetic aperture radar (SAR) data from the **Copernicus Data Space Ecosystem (CDSE)**. 

It automatically detects surface changes—specifically flood extent and inundation—by comparing Sentinel-1 radar imagery acquired before and after a disaster event for **any city or area of interest (AOI)** in the world.

### Key Capabilities
- **City-Agnostic**: Works for any location globally via simple configuration parameters.
- **Automated Footprint Screening**: Measures exact satellite swath intersection using polygon geometry to prevent clipped or partial acquisitions (solving the orbit clipping problem).
- **Metric UTM Projections**: Automatically reprojects imagery into local UTM zones (`EPSG:326xx` / `327xx`) for exact metric 20-metre pixels.
- **Dual Radiometric Quality Checks**: Validates raw backscatter intensity, enforces a strict $>90\%$ valid-pixel guardrail, and separates new inundation from permanent water.
- **Export-Ready Products**: Produces GIS-compatible GeoTIFFs, standard GeoJSON vector polygons, and executive preview graphics.

---

## 2. Directory Structure

```text
V2 COPERNICU/
├── config.yaml               # Active run configuration (AOI, date, parameters)
├── config_lucknow.yaml       # Example config for Lucknow, India
├── pipeline_utils.py         # Shared helpers (CDSE auth, UTM projection, bbox math)
├── 01_catalog.py             # Stage 1: CDSE STAC search & swath footprint coverage check
├── 02_fetch.py               # Stage 2: Sentinel Hub Process API fetch (metric UTM GeoTIFFs)
├── 03_validate.py            # Stage 3: GeoTIFF integrity, grid alignment & valid-pixel audit
├── 04_process.py             # Stage 4: Differential dB calculation, thresholding & vectorization
├── 05_visualize.py           # Stage 5: Diagnostic previews & 4-panel executive summary
├── run_pipeline.py           # Master CLI orchestrator (chains Stages 1 to 5)
├── .env                      # CDSE OAuth credentials (CDSE_CLIENT_ID, CDSE_CLIENT_SECRET)
└── runs/                     # Isolated output folder for each run
    ├── kerala_2018-08-10/    # Historical Kerala flood run
    └── lucknow_2026-10-01/   # Lucknow run
```

---

## 3. Setup & Authentication

### 1. Environment Credentials
Create a `.env` file in the project root:
```dotenv
CDSE_CLIENT_ID=your_cdse_oauth_client_id
CDSE_CLIENT_SECRET=your_cdse_oauth_client_secret
```
*(Credentials can be obtained for free from the [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/).)*

### 2. Python Dependencies
Ensure required packages are installed:
```powershell
py -m pip install requests python-dotenv rasterio numpy matplotlib shapely scipy pyyaml
```

---

## 4. How to Configure and Run

### Step 1: Set Your Target Location & Event
Open `config.yaml` and configure your event. You can specify location in two ways:

#### Option A: Center Point & Extent (Recommended)
```yaml
name: "patna"
event_date: "2024-08-15"

center_lat: 25.594
center_lon: 85.137
size_km: 30.0             # Automatically builds a 30 km x 30 km box
```

#### Option B: Explicit Bounding Box
```yaml
name: "patna"
event_date: "2024-08-15"

bbox: [85.00, 25.45, 85.30, 25.75]  # [west, south, east, north] in WGS84
```

### Step 2: Run the Pipeline
Execute the master orchestrator:
```powershell
py run_pipeline.py --config config.yaml
```

### Optional Command-Line Overrides
You can also run ad-hoc analyses without modifying configuration files:
```powershell
# Run a specific city directly via CLI
py run_pipeline.py --city mumbai --event-date 2024-07-25

# Force re-download and re-processing
py run_pipeline.py --config config.yaml --force

# Manually pick a specific acquisition pair from Stage 1 (e.g., Rank 2)
py run_pipeline.py --config config.yaml --pick PAIR_02

# Run only up to a specific stage (e.g., Stage 3)
py run_pipeline.py --config config.yaml --stage 3
```

---

## 5. Pipeline Stages Explained

```text
[config.yaml]
      │
      ▼
01_catalog.py   ──► STAC search; intersects swath polygons; filters <95% coverage; ranks pairs
      │
      ▼
02_fetch.py     ──► Process API download in auto-computed metric UTM zone (EPSG:326xx)
      │
      ▼
03_validate.py  ──► GeoTIFF audit; asserts >90% valid pixels; verifies pre/post grid parity
      │
      ▼
04_process.py   ──► Linear-to-dB conversion; permanent water masking; candidate vectorization
      │
      ▼
05_visualize.py ──► Diagnostic previews, ΔVV histogram, and 2x2 executive summary panel
      │
      ▼
[report.md]     ──► Human-readable summary report with top flood clusters and provenance
```

### Stage 1: Catalogue Screening (`01_catalog.py`)
- Searches Sentinel-1 IW GRD products in windows before and after `event_date`.
- Calculates polygon intersection between the AOI and the actual satellite swath footprint.
- **Why this matters**: A satellite swath pass may touch an AOI but only cover 1% of it (as seen in Lucknow with Orbit 92). The pipeline automatically identifies and rejects such passes, selecting only orbits with $\ge 95\%$ coverage.

### Stage 2: Metric UTM Fetching (`02_fetch.py`)
- Automatically maps coordinates to the appropriate Universal Transverse Mercator (UTM) zone.
- Requests orthorectified (`COPERNICUS_30` DEM) and Lee speckle-filtered (3×3) Float32 linear backscatter from the Process API.
- Implements atomic writes (`.part` $\to$ `.tif`) and retry logic.

### Stage 3: Data Quality & Grid Validation (`03_validate.py`)
- Confirms CRS, dimensions, and transform parity between pre and post acquisitions.
- Checks that linear backscatter power has no negative values.
- Fails loudly if valid-pixel coverage is $<90\%$, ensuring no corrupted or partial rasters enter analysis.

### Stage 4: Radiometric Processing & Inundation Extraction (`04_process.py`)
- Converts linear power to decibels: $\text{dB} = 10 \log_{10}(\text{power})$.
- Calculates differential backscatter: $\Delta\text{VV} = \text{post}_{\text{dB}} - \text{pre}_{\text{dB}}$.
- Excludes permanent water bodies (areas with pre-event $\text{VV} < -16\text{ dB}$ and $\text{VH} < -23\text{ dB}$).
- Identifies new inundation using adaptive thresholding ($\Delta\text{VV} < \mu - 1.5\sigma$).
- Discards isolated speckle clusters below `min_area_m2` and exports vector polygons to `candidates.geojson`.

### Stage 5: Preview Generation (`05_visualize.py`)
- Exports publication-ready PNG previews to `previews/` for immediate inspection without GIS desktop software.

---

## 6. Output Artifacts

Every run creates a dedicated folder: `runs/<name>_<event_date>/`:

| File | Type | Description |
|---|---|---|
| **`report.md`** | Markdown | Executive summary detailing AOI, satellite IDs, validation stats, and top flood clusters. |
| **`candidates.geojson`** | GeoJSON | Vectorized flood polygons with area in hectares and centroid coordinates. |
| **`change_mask.tif`** | GeoTIFF | Georeferenced binary raster (1 = candidate flood, 0 = no change, 255 = nodata). |
| **`metadata.json`** | JSON | Full technical provenance, band statistics, and execution audit log. |
| **`candidates.json`** | JSON | All catalogue candidates discovered with coverage percentages. |
| **`data/pre_<date>.tif`** | GeoTIFF | Metric UTM orthorectified pre-event VV/VH raster. |
| **`data/post_<date>.tif`** | GeoTIFF | Metric UTM orthorectified post-event VV/VH raster. |
| **`previews/summary_panel.png`** | Image | 4-panel executive dashboard (Pre VV, Post VV, ΔVV, Mask Overlay). |
| **`previews/change_mask_overlay.png`** | Image | Post-event satellite image with candidate flood clusters highlighted in bright cyan. |
| **`previews/delta_vv_db.png`** | Image | Diverging difference map showing backscatter drops. |
| **`previews/delta_vv_histogram.png`** | Image | Distribution of backscatter changes with marked detection threshold. |

---

## 7. Limitations & Operational Guidance

- **Specular Reflection**: Calm open water reflects radar pulses away from the sensor, producing a sharp drop in backscatter. However, high winds can roughen water surfaces and increase backscatter, potentially reducing detection contrast.
- **Urban & Dense Canopy**: Radar signals can exhibit complex multi-bounce scattering in dense city centres or dense forest canopies. Detections in built-up areas should be reviewed alongside terrain elevation and drainage maps.
- **Human Review**: This pipeline is a **decision-support tool**. Candidate flood polygons highlight priority inspection zones and should be corroborated with local situation reports and weather data before directing emergency relief.
