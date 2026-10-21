## Project README and AI Agent Context

**Project category:** Earth Observation (EO), geospatial analytics, remote sensing, AI/ML, disaster-response decision support  
**Current working directory:** `C:\Users\Sarvesh Pillai\Videos\bhumi-deploy-ready\V2 COPERNICU`  
**Current acquisition source:** Copernicus Data Space Ecosystem (CDSE) / Sentinel-1 GRD  
**Current stage:** Satellite acquisition works; raster coverage, grid semantics, and alignment must be investigated before trusting change maps.

> **Purpose:** This README is a handoff document for a coding agent. It describes the project goal, current verified state, current files and data, known problems, expected pipeline, technical guardrails, and the next actions. The agent must inspect the repository before assuming that every described file or implementation detail is still present.

---

## 1. Project mission

Build a real, reproducible system that compares satellite observations from before and after a disaster and converts meaningful surface changes into an explainable, georeferenced priority map for human responders.

The intended use cases include:
- Flood extent and likely inundation mapping
- Cyclone-related surface changes
- Landslide candidate detection
- Wildfire-related surface change
- General rapid post-event change intelligence

The system should not stop at displaying raw satellite images. It should progress from **satellite data → quality checks → aligned observations → change features → candidate detections → geospatial outputs → evidence-based priority ranking → map and export**.

The product is a **decision-support tool**, not an autonomous authority declaring damage or directing emergency operations. All detections must retain uncertainty, provenance, and review status.

## 2. Product goals

### Functional goals
1. Accept an area of interest (AOI), event type, and event date/time.
2. Find suitable satellite acquisitions before and after the event.
3. Retrieve imagery or raster products from a documented source.
4. Record acquisition metadata and request parameters.
5. Validate that data are real, non-empty, adequately covered, and usable.
6. Preprocess the data while preserving geospatial alignment.
7. Generate interpretable change features.
8. Apply a suitable baseline algorithm and, later, an evaluated ML model.
9. Convert detections into georeferenced rasters and/or vector features.
10. Rank candidate areas using transparent evidence and uncertainty.
11. Display results on a map with legends, dates, provenance, and limitations.
12. Export results and metadata so another person can reproduce the analysis.

### Non-functional goals
- Reproducibility and traceability
- Useful errors and logs
- Secure credential handling
- Modular provider/model integrations
- Honest no-data and failure handling
- Clear separation of observations, derived features, predictions, and verified facts
- No fabricated satellite measurements, locations, reports, or model accuracy claims

## 3. Current repository context

Current working directory reported in PowerShell:

```text
C:\Users\Sarvesh Pillai\Videos\bhumi-deploy-ready\V2 COPERNICU
```

Known or expected files from the current workflow:

```text
V2 COPERNICU/
├── .env
├── cdse_process.py
├── check_s1_catalog.py
├── check_rasters.py              # proposed diagnostic script; verify whether created
└── data/
    ├── pre_2026-09-22.tif
    ├── post_2026-10-04.tif
    ├── acquisition_metadata.json
    └── previews/
```

This is not a guarantee of the exact current repository structure. Inspect the folder, code, requirements, Git status, and metadata before editing. Do not overwrite unrelated files or assume that a proposed script already exists.

### Current files
- `cdse_process.py`: downloader and basic raster validator using CDSE.
- `check_s1_catalog.py`: catalogue search script used to discover Sentinel-1 acquisitions.
- `data/pre_2026-09-22.tif`: current pre-event candidate raster.
- `data/post_2026-10-04.tif`: current post-event candidate raster.
- `data/acquisition_metadata.json`: metadata file written by the download workflow.
- `data/previews/`: intended directory for PNG previews and diagnostic plots.

## 4. Current data provider and authentication

The downloader uses Copernicus Data Space Ecosystem OAuth client credentials and the Sentinel Hub Process API.

Endpoints observed in the existing script:

```text
OAuth:
https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token

Process API:
https://sh.dataspace.copernicus.eu/process/v1

Catalogue API:
https://sh.dataspace.copernicus.eu/catalog/v1/search
```

Environment variable names used by the script:

```dotenv
CDSE_CLIENT_ID=...
CDSE_CLIENT_SECRET=...
```

The actual credential values must remain private. Never put them in source code, logs, terminal output, screenshots, README content, Git commits, or agent responses. Keep `.env` out of version control.

Before changing the API request, verify current request schema, collection names, units, processing options, and output-grid semantics against current official CDSE/Sentinel Hub documentation. Do not assume that a TIFF returned by the API necessarily has adequate coverage or correct scientific properties.

## 5. Current Sentinel-1 configuration

The existing downloader has been configured for Sentinel-1 Ground Range Detected (GRD), Interferometric Wide (IW) mode, dual VV/VH polarization.

Reported request settings:

| Setting | Current value |
|---|---|
| Collection/type | `sentinel-1-grd` |
| Acquisition mode | `IW` |
| Polarization | `DV` |
| Bands | `VV`, `VH` |
| Output bands | 2 |
| Output data type | Float32 |
| Requested nominal resolution | 20 m |
| Bounding box | `[80.85, 26.75, 81.05, 26.95]` |
| Orbit direction | `DESCENDING` |
| UTC time window | `00:25:00`–`00:31:00` |
| Backscatter processing setting reported in script | `SIGMA0_ELLIPSOID` |
| Orthorectification | Enabled |
| DEM | Copernicus 30 m |
| Speckle filter | Lee, 3×3 |

The exact configuration must be confirmed by inspecting `cdse_process.py`. The table records the current working context, not an assertion that every parameter is scientifically optimal.

## 6. Acquisition discovery and selected dates

The catalogue query returned candidate Sentinel-1 acquisitions intersecting the AOI.

| Date | Acquisition time (UTC) | Orbit | Relative orbit | Mode | Polarizations |
|---|---|---|---:|---|---|
| 2026-09-22 | 00:27:41–00:28:06 | Descending | 92 | IW | VV/VH |
| 2026-10-04 | 00:27:41–00:28:06 | Descending | 92 | IW | VV/VH |

Catalogue item IDs reported:

```text
S1D_IW_GRDH_1SDV_20260922T002741_20260922T002806_004683_008C06_19EF_COG.SAFE
S1D_IW_GRDH_1SDV_20261004T002741_20261004T002806_004858_00921F_F481_COG.SAFE
```

These dates were chosen because the catalogue reported the same descending relative orbit, IW mode, and VV/VH polarizations, with similar acquisition times. This is a useful first filter for comparability, but it does not prove sub-pixel co-registration, identical coverage, or radiometric equivalence.

Other acquisitions reported in the broader search:
- 2026-09-19: ascending, relative orbit 56
- 2026-09-27: descending, relative orbit 165
- 2026-10-01: ascending, relative orbit 56
- 2026-10-09: descending, relative orbit 165

The Sep 22 / Oct 4 pair was preferred for a same-relative-orbit comparison.

**Critical unknown:** The actual disaster type and event date/time have not been confirmed in the current context. Do not claim that these acquisitions bracket a real disaster until the user confirms the event and timing. For now, call them the *candidate pre/post pair* or *technical test pair*.

## 7. Command used to download the current rasters

The most recent successful command was:

```powershell
py cdse_process.py --bbox 80.85 26.75 81.05 26.95 --pre-date 2026-09-22 --post-date 2026-10-04 --orbit DESCENDING --time-start 00:25:00 --time-end 00:31:00
```

The script authenticated successfully, downloaded both outputs, and passed its basic structural and pixel checks.

## 8. Latest observed raster validation

### Pre-event candidate
File: `data/pre_2026-09-22.tif`

- File size: approximately 0.093 MB
- Dimensions: 993 × 1105
- Bands: 2
- CRS: EPSG:4326
- Data types: Float32, Float32
- Bounds: west 80.85, south 26.75, east 81.05, north 26.95
- VV valid pixels: 10,309
- VV minimum: 0.002858227
- VV maximum: 96.83944
- VV standard deviation: 1.43097
- VH valid pixels: 10,309
- VH minimum: 0.0003070528
- VH maximum: 10.42551
- VH standard deviation: 0.1937994

### Post-event candidate
File: `data/post_2026-10-04.tif`

- File size: approximately 0.091 MB
- Dimensions: 993 × 1105
- Bands: 2
- CRS: EPSG:4326
- Data types: Float32, Float32
- Bounds: west 80.85, south 26.75, east 81.05, north 26.95
- VV valid pixels: 9,906
- VV minimum: 0.002602509
- VV maximum: 226.6085
- VV standard deviation: 3.338585
- VH valid pixels: 9,906
- VH minimum: 0.0003586703
- VH maximum: 32.56171
- VH standard deviation: 0.4255378

The script reported:

```text
PHASE 1B COMPLETED
Both rasters passed basic structural and pixel checks.
IMPORTANT: Confirm exact acquisition timestamps and relative orbit compatibility before change detection.
```

### What this proves
- Both files are readable rasters.
- Each has two Float32 bands.
- The reported arrays have non-constant valid measurements.
- The downloader and basic validation ran to completion.

### What this does not prove
- Full or adequate AOI coverage
- Correct interpretation of masks and no-data
- Correct ground sampling distance in metres
- Accurate co-registration
- Appropriate radiometric units and calibration for change detection
- That the selected pair brackets a real disaster
- That any change is caused by flooding or another disaster

### Major issue: sparse valid coverage
The raster grid contains:

`993 × 1105 = 1,097,265` pixels.

A valid count around 10,000 is **under 1% of the full grid**, assuming the printed count represents valid cells per band. This is the most urgent problem. The agent must diagnose why coverage is sparse before trusting any visual preview or change map.

Do not “fix” this by disabling validation, filling missing values with zero, or generating synthetic pixel values. Investigate the mask, nodata metadata, request geometry, Process API request and response, output grid, and the meaning of the requested resolution.

## 9. Immediate priority: diagnose raster coverage

Before model development, inspect:
1. `cdse_process.py` request body and evalscript.
2. `data/acquisition_metadata.json`.
3. Raster `nodata` values, band masks, dataset mask, block layout, compression, dtype, transform, and pixel sizes.
4. Validity masks for all bands/dates.
5. API response headers and request identifiers where available (without secrets).
6. Actual output-grid behavior for EPSG:4326 and the requested 20 m resolution.
7. Whether the Process API output grid is correctly specified and whether the returned raster is a full AOI or mostly masked.
8. Whether the script’s validation counts valid values or only checks a subset of mask semantics.

Produce a diagnostic report with:
- Full grid size and valid percentage per band/date
- Dataset mask and per-band mask summaries
- Nodata metadata and finite/zero/negative counts
- Affine transform and pixel size in CRS units
- Valid-data footprint previews
- Process API request parameters (credentials redacted)
- A reasoned explanation of the coverage issue and a tested fix

Do not re-download repeatedly with arbitrary changes. First establish what the existing request actually returns and why.

## 10. Raster preview and preliminary change workflow

A script called `check_rasters.py` has been proposed. Confirm whether it exists; if not, create it in the project root. It should use the current 2026 filenames, not old 2018 filenames.

Expected responsibilities:
- Read TIFFs with `rasterio.open(...).read(masked=True)`.
- Respect nodata and masks; do not assume zero is always invalid.
- Convert masked or non-finite values to NaN for calculations.
- Print dimensions, CRS, bounds, affine transform, pixel size, band count, valid counts, and valid percentages.
- Compare shape, CRS, and full affine transforms.
- Plot pre VV, pre VH, post VV, post VH.
- Plot validity masks separately so sparse coverage is obvious.
- Convert positive linear power to dB if the units are confirmed to be linear power.
- Calculate preliminary temporal differences only where both dates are valid.
- Save diagnostic images under `data/previews/`.
- Print shared valid-pixel counts and robust change statistics.

Expected PNGs may include:

```text
data/previews/pre_vv.png
data/previews/pre_vh.png
data/previews/post_vv.png
data/previews/post_vh.png
data/previews/pre_valid_mask.png
data/previews/post_valid_mask.png
data/previews/vv_change.png
data/previews/vh_change.png
```

Run:

```powershell
py check_rasters.py
```

Install missing dependencies only if necessary:

```powershell
py -m pip install rasterio numpy matplotlib
```

If a virtual environment or `requirements.txt` exists, use the project’s existing environment instead of creating dependency conflicts.

## 11. Spatial grid, resolution, and co-registration

The current output reports `EPSG:4326`. This CRS uses angular degrees as coordinate units, not metres. Therefore, a requested “20 m” resolution must not be assumed to equal a 20-metre pixel just because the command requested it.

The agent must inspect:
- The raster affine transform
- Pixel width and height in CRS units
- Actual output width/height
- How the Process API maps requested resolution to the output grid
- Whether the bbox and output dimensions are consistent with the requested grid

If a metric grid is required, consider an appropriate projected CRS for the AOI and ensure the API or a deliberate reprojection step uses that grid correctly. Document any reprojection and resampling.

Matching dimensions, bounds, CRS, and transform is necessary for straightforward pixel-wise comparisons, but not sufficient to prove physical co-registration. If grids differ, align/resample before comparing. Then assess feature alignment independently.

## 12. Linear power and dB

The downloader reportedly requests `LINEAR_POWER`. If inspection confirms that the band values are linear power, the conversion is:

`dB = 10 × log10(power)`

Use only positive valid values. Preserve masks and NaNs. Do not use `20 × log10(power)` for power data.

Verify the exact requested output units and processing settings in `cdse_process.py` and metadata before conversion. Do not assume the API output units solely from the variable name.

## 13. Meaning and limitations of the change map

A basic change feature is:

`change_dB = post_dB - pre_dB`

Interpretation:
- Positive: post-date backscatter is higher.
- Negative: post-date backscatter is lower.
- Near zero: little change in this particular backscatter feature.

This is a **change indicator, not a flood classifier**. Radar backscatter response depends on land cover, vegetation, buildings, water surface roughness, incidence geometry, wind, soil moisture, seasonal changes, and processing choices. Smooth open water can reduce backscatter, but vegetation and built-up areas can behave differently.

The 2nd–98th percentile stretch may be used for visualization, but it is not a classification threshold. Keep display clipping separate from analytical values. No-data must be visually distinct from “no change”.

## 14. Proposed end-to-end architecture

```text
AOI + event date/type
        |
        v
Acquisition discovery
        |
        v
Suitability screening
(time, orbit, polarization, mode, AOI intersection)
        |
        v
Download and provenance capture
        |
        v
Raster integrity + coverage validation
        |
        v
Preprocessing
(masking, units, alignment, optional filtering)
        |
        v
Feature engineering
(VV/VH dB, temporal differences, ratios, context)
        |
        v
Baseline change detector
        |
        v
ML classifier/segmentation (after validation data exist)
        |
        v
Geospatial post-processing
(polygons, areas, region aggregation)
        |
        v
Evidence-based priority scoring
        |
        v
Map, downloadable layers, report, human review
```

Keep each stage modular, with explicit input/output contracts. Fail early if a stage receives insufficient coverage, incompatible grids, missing metadata, or invalid units.

## 15. AI/ML responsibilities

Use raster/geospatial algorithms or trained models for actual pixel-level change detection. Do not ask an LLM to infer pixel coordinates from prose or to invent map geometry.

A sensible development path:
1. Reliable acquisition and raster validation.
2. Reproducible, interpretable change-feature baseline.
3. A rule-based candidate detector for initial exploration.
4. Labelled/independent data collection and evaluation.
5. Model selection appropriate to the event type and available labels.
6. Calibration and uncertainty reporting.
7. Human review and error analysis.
8. Deployment only after realistic evaluation.

Possible methods depend on the task and data availability: thresholding, change-vector features, random forests, gradient boosting, or segmentation networks. Do not select a complex model before understanding the data and defining labels.

Track false positives, false negatives, precision/recall, IoU/F1 where suitable, and performance across different land covers and events. Do not invent metrics.

## 16. RAG and LLM responsibilities

RAG is a supporting evidence and context layer, not the image-analysis engine.

Useful source collections may include:
- Official disaster bulletins and situation reports
- Authoritative meteorological/hydrological warnings
- Verified administrative boundaries and place-name datasets
- Roads, hospitals, shelters, and critical infrastructure from reputable datasets
- Official response guidelines
- Dataset/model documentation and known limitations
- Time-stamped field reports, if they are sourced and permissioned

Each retrieved record should retain source, publication time, retrieval time, geographic scope, and a link or identifier. The LLM may summarize evidence, explain why an area was prioritized, and answer operator questions with citations.

The LLM must not:
- Invent satellite acquisitions or source documents
- Generate precise coordinates from ambiguous prose without a validated geocoder/data source
- Claim that a detected change is a confirmed flood without evidence
- Replace geospatial processing
- Hide uncertainty or present unverified social posts as authoritative facts

## 17. Candidate region output contract

A future detection output could follow this schema. It is an example only, not a real detection:

```json
{
  "region_id": "stable-generated-id",
  "geometry": {
    "type": "Polygon",
    "coordinates": []
  },
  "change_type": "candidate_change",
  "score": null,
  "confidence": "unvalidated",
  "evidence": {
    "pre_acquisition_id": "catalogue-item-id",
    "post_acquisition_id": "catalogue-item-id",
    "vv_change_db_summary": {},
    "vh_change_db_summary": {},
    "valid_data_fraction": null
  },
  "context_sources": [],
  "limitations": [
    "Candidate change is not a confirmed disaster impact."
  ],
  "review_status": "requires_human_review"
}
```

Use real geometries and real computed values only in actual output. Distinguish model confidence from response priority.

## 18. Priority scoring principles

A future priority score may combine:
- Magnitude and spatial extent of observed change
- Reliability and coverage of satellite evidence
- Recency of acquisition
- Corroboration from authoritative reports
- Proximity to verified population or critical infrastructure
- Uncertainty and data-quality limitations
- Human review status

Keep component scores visible, weights configurable, and reasoning inspectable. Do not use invented population values, facility coordinates, or damage labels. The map should help people decide what to inspect first; it must not imply autonomous emergency authority.

## 19. Environment and local commands

Recommended baseline dependencies are `requests`, `python-dotenv`, `rasterio`, `numpy`, and `matplotlib`. Inspect the existing environment and dependency files first.

If there is no existing environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install requests python-dotenv rasterio numpy matplotlib
```

Useful checks:

```powershell
py --version
py -m pip show requests python-dotenv rasterio numpy matplotlib
Test-Path .env
Test-Path data\pre_2026-09-22.tif
Test-Path data\post_2026-10-04.tif
```

`Test-Path .env` only checks that the file exists, not that credentials are correct.

## 20. Git and secret hygiene

Ensure the repository ignores at least the following as appropriate:

```gitignore
.env
.venv/
__pycache__/
*.py[cod]
data/*.part.tif
```

Whether to track final TIFFs depends on repository size, licensing, reproducibility, and team workflow. Do not commit credentials. Do not automatically delete data or modify Git history.

## 21. Testing checklist

### Acquisition
- [ ] Authentication works without logging secrets.
- [ ] Catalogue items exist and intersect the AOI.
- [ ] Acquisition timestamps, orbit, relative orbit, mode, and polarization are recorded.
- [ ] API errors are not saved as TIFFs.
- [ ] TIFFs are readable and contain expected bands.
- [ ] Valid-data coverage is measured and meets a configurable threshold.
- [ ] Processing options and output units are recorded.
- [ ] Failed or incomplete requests fail clearly.

### Raster quality
- [ ] Band order is confirmed.
- [ ] Dataset and band masks are inspected.
- [ ] Nodata values and zero values are treated correctly.
- [ ] CRS, affine transform, bounds, and actual pixel size are reported.
- [ ] Pre/post grids match or are deliberately aligned.
- [ ] Common-valid coverage is measured.
- [ ] Co-registration is evaluated.
- [ ] dB conversion uses the correct units and positive valid pixels only.

### Detection
- [ ] Baseline outputs are reproducible.
- [ ] Missing pixels are excluded from detection and statistics.
- [ ] Thresholds are calibrated and documented.
- [ ] Results are compared against independent evidence/labels where possible.
- [ ] Uncertainty and known limitations are preserved.
- [ ] Candidate changes are not represented as confirmed damage without corroboration.

### Map and reporting
- [ ] Geometry and CRS are correct.
- [ ] Legend explains values, score, and confidence.
- [ ] No-data is visibly different from no change.
- [ ] Every feature has provenance and review status.
- [ ] Exports preserve acquisition dates and processing metadata.

## 22. Known risks and unanswered questions

1. **Event details:** What exact disaster and event date are being analyzed?
2. **Sparse coverage:** Why do the rasters have fewer than 1% valid cells?
3. **Output grid:** Is the output actually at 20 m, given the reported EPSG:4326 CRS?
4. **Masks:** Does the valid-pixel count correctly respect per-band masks and nodata?
5. **Radiometry:** Are the output values confirmed to be linear power and processed as intended?
6. **Alignment:** Are the raster grids identical, and are ground features accurately co-registered?
7. **Ground truth:** What independent evidence or labelled data will be used to evaluate detection?
8. **Application architecture:** What frontend/backend/map framework exists in the repository? Inspect before deciding or refactoring.
9. **Operational use:** What latency, geographic coverage, and data-quality thresholds are required?

## 23. Instructions to the coding agent

Follow these rules while working in the repository:

1. **Inspect before editing.** Read existing scripts, metadata, dependency files, folder structure, and Git status.
2. **Address sparse coverage first.** It is the most urgent known technical issue.
3. **Verify API contracts.** Use official, current CDSE/Sentinel Hub documentation before changing request parameters.
4. **Preserve working behavior.** Authentication and TIFF download already succeeded. Do not rewrite the whole downloader without identifying a specific cause or improvement.
5. **Do not fabricate data.** Never synthesize missing pixels or substitute zero for no-data.
6. **Do not overclaim.** A valid TIFF is not proof of valid coverage; a difference image is not proof of flooding.
7. **Protect credentials.** Redact tokens and secrets from logs and outputs.
8. **Make minimal, testable changes.** Explain changed files, rationale, commands, expected outputs, and remaining limitations.
9. **Keep provenance.** Preserve catalogue IDs, acquisition metadata, request parameters, units, masks, and validation results.
10. **Do not invent architecture.** Inspect the actual project before selecting a frontend, backend, database, model, or deployment strategy.
11. **Separate geospatial computation from RAG.** The raster/ML pipeline computes detections; RAG provides source-grounded contextual evidence.
12. **Human review remains part of the workflow.** Expose uncertainty and evidence instead of presenting the output as unquestionable truth.

## 24. Immediate execution plan

Execute in this order:

1. Inspect `cdse_process.py`, `check_s1_catalog.py`, and `data/acquisition_metadata.json`.
2. Inspect both TIFFs' nodata, dataset/per-band masks, affine transforms, CRS, dimensions, and pixel sizes.
3. Generate validity-mask images and quantify valid coverage for every date/band.
4. Explain why only around 10,000 out of 1,097,265 cells are reported valid.
5. Verify the Process API output-grid/resolution configuration and actual units.
6. Make the smallest justified correction and re-run acquisition only after diagnosis.
7. Confirm sufficient overlapping coverage.
8. Check spatial alignment/co-registration.
9. Generate VV/VH previews and preliminary change layers.
10. Confirm the actual disaster date and type.
11. Build and evaluate a baseline detector.
12. Add ML, contextual RAG, priority scoring, and map integration only after the data pipeline is trustworthy.

---

## Quick-start summary for an agent

This repository is a real satellite-based post-disaster change-intelligence prototype. The current directory is `C:\Users\Sarvesh Pillai\Videos\bhumi-deploy-ready\V2 COPERNICU`. The script `cdse_process.py` authenticates with CDSE and downloads Sentinel-1 GRD VV/VH Float32 GeoTIFFs for bbox `[80.85, 26.75, 81.05, 26.95]`. The current candidate acquisitions are 2026-09-22 and 2026-10-04, both reported as descending relative orbit 92, IW mode, VV/VH. Files: `data/pre_2026-09-22.tif` and `data/post_2026-10-04.tif`. Each raster is reported as 993×1105 in EPSG:4326, but only approximately 10,000 of 1,097,265 pixels are reported valid per band (less than 1%). **First diagnose sparse valid coverage, masks, actual pixel size, output units, and alignment. Do not trust or classify the change map until these issues are resolved.** The actual disaster type/date are still unconfirmed. Do not fabricate data or credentials, and do not call candidate changes confirmed flood damage.
"""