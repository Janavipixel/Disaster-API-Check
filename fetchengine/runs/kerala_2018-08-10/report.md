# Sentinel-1 Change Intelligence Report: Kerala

**Event Date:** `2018-08-10`  
**Run Identifier:** `kerala_2018-08-10`  
**Target Coordinate System:** `EPSG:32643` (UTM Metric)  
**Bounding Box (WGS84):** `West: 76.2, South: 9.8, East: 76.6, North: 10.2`  
**Requested Spatial Resolution:** `20.0 m` (Effective: `20.0 m`)  

---

## 1. Satellite Acquisitions & Provenance

- **Relative Orbit:** `165` (DESCENDING)
- **AOI Coverage Footprint:** Pre-Event `100.0%`, Post-Event `100.0%`
- **Pre-Event Acquisition:** `2018-08-09T00:40:43Z` (`S1A_IW_GRDH_1SDV_20180809T004043_20180809T004108_023162_02842B_F9CD_COG.SAFE`)
- **Post-Event Acquisition:** `2018-08-21T00:40:44Z` (`S1A_IW_GRDH_1SDV_20180821T004044_20180821T004109_023337_0289D5_9B06_COG.SAFE`)
- **Time Gap to Event:** Pre `0.97 days`, Post `11.03 days`

## 2. Raster Validation & Grid Quality

- **Grid Dimensions:** `2202 x 2221` pixels
- **Common Valid Overlap:** `4,890,642` pixels (`100.0%`)
- **Radiometric Calibration:** Linear Sigma0 power orthorectified via `COPERNICUS_30` DEM with 3x3 Lee speckle filtering.
- **Negative Power Check:** Passed (0 negative values).

## 3. Change Detection & Inundation Analysis

- **Detection Method:** `Adaptive (mean - 1.5*std) clamped: -3.25 dB (mean=0.11, std=2.24)`
- **Selected Inundation Threshold:** `-3.25 dB`
- **Permanent Water Excluded:** `690,793` pixels
- **Candidate Regions Detected:** `4,360` clusters
- **Total Detected Flood Area:** `4,070.9 ha` (`40.71 km²`)

### Top Detected Change Clusters (by Area)

| Cluster ID | Area (ha) | Area (km²) | Centroid Lat | Centroid Lon |
|---|---|---|---|---|
| `cand_0001` | 164.05 | 1.6405 | 10.192176 | 76.281867 |
| `cand_0002` | 132.41 | 1.3241 | 10.183841 | 76.25877 |
| `cand_0003` | 84.96 | 0.8496 | 10.168209 | 76.3242 |
| `cand_0004` | 69.56 | 0.6956 | 9.860291 | 76.373612 |
| `cand_0005` | 66.8 | 0.668 | 10.173068 | 76.336924 |

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
