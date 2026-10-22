# Sentinel-1 Change Intelligence Report: Nepal_Trishuli_Landslide

**Event Date:** `2026-08-26`  
**Run Identifier:** `nepal_trishuli_landslide_2026-08-26`  
**Target Coordinate System:** `EPSG:32645` (UTM Metric)  
**Bounding Box (WGS84):** `West: 85.1, South: 27.88, East: 85.56, North: 28.34`  
**Requested Spatial Resolution:** `20.0 m` (Effective: `20.64 m`)  

---

## 1. Satellite Acquisitions & Provenance

- **Relative Orbit:** `85` (ASCENDING)
- **AOI Coverage Footprint:** Pre-Event `100.0%`, Post-Event `100.0%`
- **Pre-Event Acquisition:** `2026-08-16T12:21:41Z` (`S1D_IW_GRDH_1SDV_20260816T122141_20260816T122206_004151_007980_B091_COG.SAFE`)
- **Post-Event Acquisition:** `2026-08-28T12:21:41Z` (`S1D_IW_GRDH_1SDV_20260828T122141_20260828T122206_004326_007FA4_C73B_COG.SAFE`)
- **Time Gap to Event:** Pre `9.48 days`, Post `2.52 days`

## 2. Raster Validation & Grid Quality

- **Grid Dimensions:** `2223 x 2500` pixels
- **Common Valid Overlap:** `5,557,500` pixels (`100.0%`)
- **Radiometric Calibration:** Linear Sigma0 power orthorectified via `COPERNICUS_30` DEM with 3x3 Lee speckle filtering.
- **Negative Power Check:** Passed (0 negative values).

## 3. Change Detection & Inundation Analysis

- **Detection Method:** `Adaptive (mean - 2.0*std) clamped: -3.74 dB (mean=0.01, std=1.87)`
- **Selected Inundation Threshold:** `-3.74 dB`
- **Permanent Water Excluded:** `245,206` pixels
- **Candidate Regions Detected:** `8,638` clusters
- **Total Detected Flood Area:** `1,860.0 ha` (`18.60 km²`)

### Top Detected Change Clusters (by Area)

| Cluster ID | Area (ha) | Area (km²) | Centroid Lat | Centroid Lon |
|---|---|---|---|---|
| `cand_0001` | 27.14 | 0.2714 | 28.28591 | 85.524875 |
| `cand_0002` | 12.87 | 0.1287 | 28.289979 | 85.527007 |
| `cand_0003` | 11.16 | 0.1116 | 28.333056 | 85.483612 |
| `cand_0004` | 9.12 | 0.0912 | 27.974515 | 85.187597 |
| `cand_0005` | 7.58 | 0.0758 | 28.284583 | 85.515167 |

## 4. Diagnostic Preview Gallery

- **Summary Panel (2x2):** `previews/summary_panel.png`
- **Inundation Detections Overlay:** `previews/change_mask_overlay.png`
- **Backscatter Difference (ΔVV):** `previews/delta_vv_db.png`
- **ΔVV Histogram & Cutoff:** `previews/delta_vv_histogram.png`
- **Pre-Event VV Backscatter:** `previews/pre_vv_db.png`
- **Post-Event VV Backscatter:** `previews/post_vv_db.png`

## 5. Artifacts and Exports

- `change_mask.tif`: Binary GeoTIFF mask (1 = candidate inundation, 0 = no change, 255 = nodata).
- `candidates.geojson`: Vectorized candidate polygons with computed surface areas and coordinates.
- `metadata.json`: Machine-readable provenance and validation statistics.
- `candidates.json`: Full CDSE catalogue query and relative orbit ranking.

## 6. Limitations & Human Review Disclaimer

> **Notice:** This output represents an automated change-detection indicator derived from synthetic aperture radar backscatter differences. Radar backscatter changes may be influenced by vegetation phenology, soil moisture variations, surface roughness (wind-roughened open water), and urban corner-reflectors. Detections must be reviewed alongside independent meteorological data and field reports before initiating emergency response operations.
