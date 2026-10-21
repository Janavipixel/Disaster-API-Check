# Sentinel-1 Change Intelligence Report: Lucknow

**Event Date:** `2026-10-01`  
**Run Identifier:** `lucknow_2026-10-01`  
**Target Coordinate System:** `EPSG:32644` (UTM Metric)  
**Bounding Box (WGS84):** `West: 80.85, South: 26.75, East: 81.05, North: 26.95`  
**Requested Spatial Resolution:** `20.0 m` (Effective: `20.0 m`)  

---

## 1. Satellite Acquisitions & Provenance

- **Relative Orbit:** `165` (DESCENDING)
- **AOI Coverage Footprint:** Pre-Event `100.0%`, Post-Event `100.0%`
- **Pre-Event Acquisition:** `2026-09-27T00:35:47Z` (`S1D_IW_GRDH_1SDV_20260927T003547_20260927T003612_004756_008E87_9D45_COG.SAFE`)
- **Post-Event Acquisition:** `2026-10-09T00:35:47Z` (`S1D_IW_GRDH_1SDV_20261009T003547_20261009T003612_004931_0094AF_7624_COG.SAFE`)
- **Time Gap to Event:** Pre `3.98 days`, Post `8.02 days`

## 2. Raster Validation & Grid Quality

- **Grid Dimensions:** `994 x 1108` pixels
- **Common Valid Overlap:** `1,101,352` pixels (`100.0%`)
- **Radiometric Calibration:** Linear Sigma0 power orthorectified via `COPERNICUS_30` DEM with 3x3 Lee speckle filtering.
- **Negative Power Check:** Passed (0 negative values).

## 3. Change Detection & Inundation Analysis

- **Detection Method:** `Adaptive (mean - 1.5*std) clamped: -6.00 dB (mean=-2.72, std=3.01)`
- **Selected Inundation Threshold:** `-6.0 dB`
- **Permanent Water Excluded:** `8,816` pixels
- **Candidate Regions Detected:** `6,170` clusters
- **Total Detected Flood Area:** `3,554.4 ha` (`35.54 km²`)

### Top Detected Change Clusters (by Area)

| Cluster ID | Area (ha) | Area (km²) | Centroid Lat | Centroid Lon |
|---|---|---|---|---|
| `cand_0001` | 259.81 | 2.5981 | 26.90325 | 80.891048 |
| `cand_0002` | 23.53 | 0.2353 | 26.814987 | 81.040508 |
| `cand_0003` | 23.45 | 0.2345 | 26.92313 | 80.86381 |
| `cand_0004` | 20.81 | 0.2081 | 26.912313 | 80.877376 |
| `cand_0005` | 15.97 | 0.1597 | 26.848483 | 80.87992 |

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
