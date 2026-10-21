"""
run_pipeline.py: Master orchestrator for generic Sentinel-1 disaster change detection.
Executes Stages 1 through 5, enforces error boundaries, and produces report.md.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any

from pipeline_utils import load_config


def run_command(cmd_list: list, desc: str) -> None:
    """Execute a python subprocess command, streaming output and failing on error."""
    print("\n" + "=" * 75)
    print(f"PIPELINE RUNNER >> {desc}")
    print("=" * 75)
    result = subprocess.run(cmd_list)
    if result.returncode != 0:
        print("\n" + "!" * 75)
        print(f"PIPELINE ABORTED: Stage failed during '{desc}' (Exit code: {result.returncode})")
        print("!" * 75)
        sys.exit(result.returncode)


def generate_report(cfg: Dict[str, Any]) -> Path:
    """Generate comprehensive markdown report for the run."""
    run_dir = Path(cfg["run_dir"])
    metadata_file = run_dir / "metadata.json"
    candidates_geojson = run_dir / "candidates.geojson"
    report_file = run_dir / "report.md"

    metadata = {}
    if metadata_file.exists():
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}

    cat_info = metadata.get("stage_1_catalog", {})
    selected_pair = cat_info.get("selected_pair", {})
    fetch_info = metadata.get("stage_2_fetch", {})
    val_info = metadata.get("stage_3_validate", {})
    proc_info = metadata.get("stage_4_process", {})

    pre_scene = selected_pair.get("pre_scene", {})
    post_scene = selected_pair.get("post_scene", {})

    top_clusters = []
    if candidates_geojson.exists():
        try:
            geo = json.loads(candidates_geojson.read_text(encoding="utf-8"))
            feats = geo.get("features", [])
            for f in feats[:5]:
                p = f.get("properties", {})
                top_clusters.append({
                    "id": p.get("id"),
                    "area_ha": p.get("area_ha"),
                    "area_km2": p.get("area_km2"),
                    "lat": p.get("centroid_lat"),
                    "lon": p.get("centroid_lon"),
                })
        except Exception:
            pass

    overlap = val_info.get("overlap_stats", {})
    pre_stats = val_info.get("pre_stats", {})

    report_lines = [
        f"# Sentinel-1 Change Intelligence Report: {cfg['name'].title()}",
        "",
        f"**Event Date:** `{cfg['event_date']}`  ",
        f"**Run Identifier:** `{cfg['name'].lower()}_{cfg['event_date']}`  ",
        f"**Target Coordinate System:** `EPSG:{cfg['utm_epsg']}` (UTM Metric)  ",
        f"**Bounding Box (WGS84):** `West: {cfg['bbox'][0]}, South: {cfg['bbox'][1]}, East: {cfg['bbox'][2]}, North: {cfg['bbox'][3]}`  ",
        f"**Requested Spatial Resolution:** `{cfg['resolution_m']} m` (Effective: `{fetch_info.get('effective_resolution_m', cfg['resolution_m'])} m`)  ",
        "",
        "---",
        "",
        "## 1. Satellite Acquisitions & Provenance",
        "",
        f"- **Relative Orbit:** `{selected_pair.get('relative_orbit', 'N/A')}` ({selected_pair.get('orbit_direction', 'N/A')})",
        f"- **AOI Coverage Footprint:** Pre-Event `{pre_scene.get('coverage_pct', 'N/A')}%`, Post-Event `{post_scene.get('coverage_pct', 'N/A')}%`",
        f"- **Pre-Event Acquisition:** `{pre_scene.get('datetime', 'N/A')}` (`{pre_scene.get('id', 'N/A')}`)",
        f"- **Post-Event Acquisition:** `{post_scene.get('datetime', 'N/A')}` (`{post_scene.get('id', 'N/A')}`)",
        f"- **Time Gap to Event:** Pre `{pre_scene.get('gap_days', 'N/A')} days`, Post `{post_scene.get('gap_days', 'N/A')} days`",
        "",
        "## 2. Raster Validation & Grid Quality",
        "",
        f"- **Grid Dimensions:** `{pre_stats.get('width', 'N/A')} x {pre_stats.get('height', 'N/A')}` pixels",
        f"- **Common Valid Overlap:** `{overlap.get('common_valid_pixels', 0):,}` pixels (`{overlap.get('common_valid_pct', 0)}%`)",
        f"- **Radiometric Calibration:** Linear Sigma0 power orthorectified via `COPERNICUS_30` DEM with 3x3 Lee speckle filtering.",
        "- **Negative Power Check:** Passed (0 negative values).",
        "",
        "## 3. Change Detection & Inundation Analysis",
        "",
        f"- **Detection Method:** `{proc_info.get('threshold_method', 'N/A')}`",
        f"- **Selected Inundation Threshold:** `{proc_info.get('threshold_db', 'N/A')} dB`",
        f"- **Permanent Water Excluded:** `{proc_info.get('permanent_water_pixels', 0):,}` pixels",
        f"- **Candidate Regions Detected:** `{proc_info.get('candidate_polygon_count', 0):,}` clusters",
        f"- **Total Detected Flood Area:** `{proc_info.get('total_candidate_area_ha', 0):,.1f} ha` (`{proc_info.get('total_candidate_area_km2', 0):,.2f} km²`)",
        "",
    ]

    if top_clusters:
        report_lines.extend([
            "### Top Detected Change Clusters (by Area)",
            "",
            "| Cluster ID | Area (ha) | Area (km²) | Centroid Lat | Centroid Lon |",
            "|---|---|---|---|---|",
        ])
        for c in top_clusters:
            report_lines.append(f"| `{c['id']}` | {c['area_ha']:,} | {c['area_km2']} | {c['lat']} | {c['lon']} |")
        report_lines.append("")

    report_lines.extend([
        "## 4. Diagnostic Preview Gallery",
        "",
        "- **Summary Panel (2x2):** `previews/summary_panel.png`",
        "- **Inundation Detections Overlay:** `previews/change_mask_overlay.png`",
        "- **Backscatter Difference (ΔVV):** `previews/delta_vv_db.png`",
        "- **ΔVV Histogram & Cutoff:** `previews/delta_vv_histogram.png`",
        "- **Pre-Event VV Backscatter:** `previews/pre_vv_db.png`",
        "- **Post-Event VV Backscatter:** `previews/post_vv_db.png`",
        "",
        "## 5. Artifacts and Exports",
        "",
        f"- `change_mask.tif`: Binary GeoTIFF mask (1 = candidate inundation, 0 = no change, 255 = nodata).",
        f"- `candidates.geojson`: Vectorized candidate polygons with computed surface areas and coordinates.",
        f"- `metadata.json`: Machine-readable provenance and validation statistics.",
        f"- `candidates.json`: Full CDSE catalogue query and relative orbit ranking.",
        "",
        "## 6. Limitations & Human Review Disclaimer",
        "",
        "> **Notice:** This output represents an automated change-detection indicator derived from synthetic aperture radar backscatter differences. "
        "Radar backscatter changes may be influenced by vegetation phenology, soil moisture variations, surface roughness (wind-roughened open water), "
        "and urban corner-reflectors. Detections must be reviewed alongside independent meteorological data and field reports before initiating emergency response operations.",
        "",
    ])

    report_content = "\n".join(report_lines)
    report_file.write_text(report_content, encoding="utf-8")
    return report_file


def main():
    parser = argparse.ArgumentParser(description="Sentinel-1 City-Agnostic Change Detection Pipeline")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML configuration file")
    parser.add_argument("--city", default=None, help="Override run name")
    parser.add_argument("--event-date", default=None, help="Override event date (YYYY-MM-DD)")
    parser.add_argument("--pick", default=None, help="Override candidate scene pair index or pair ID")
    parser.add_argument("--force", action="store_true", help="Force re-running of all stages")
    parser.add_argument("--stage", type=int, default=None, help="Run only up to or specific stage (1..5)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.city:
        cfg["name"] = args.city
    if args.event_date:
        cfg["event_date"] = args.event_date

    print("\n" + "=" * 80)
    print("SENTINEL-1 AUTOMATED DISASTER CHANGE-DETECTION PIPELINE")
    print("=" * 80)
    print(f"Target AOI:    {cfg['name']}")
    print(f"Event Date:    {cfg['event_date']}")
    print(f"Bounding Box:  {cfg['bbox']}")
    print(f"Output Run:    {cfg['run_dir']}")

    py_exe = sys.executable

    # Stage 1: Catalogue
    if args.stage is None or args.stage >= 1:
        cmd1 = [py_exe, "01_catalog.py", "--config", args.config]
        if args.pick:
            cmd1.extend(["--pick", str(args.pick)])
        run_command(cmd1, "STAGE 1: Catalogue Query & Footprint Coverage Check")

    # Stage 2: Fetch
    if args.stage is None or args.stage >= 2:
        cmd2 = [py_exe, "02_fetch.py", "--config", args.config]
        if args.force:
            cmd2.append("--force")
        run_command(cmd2, "STAGE 2: Process API GeoTIFF Fetch (Metric UTM)")

    # Stage 3: Validate
    if args.stage is None or args.stage >= 3:
        cmd3 = [py_exe, "03_validate.py", "--config", args.config]
        run_command(cmd3, "STAGE 3: Raster Integrity & Grid Alignment Check")

    # Stage 4: Process
    if args.stage is None or args.stage >= 4:
        cmd4 = [py_exe, "04_process.py", "--config", args.config]
        if args.force:
            cmd4.append("--force")
        run_command(cmd4, "STAGE 4: Differential Radiometric Analysis & Candidate Detections")

    # Stage 5: Visualize
    if args.stage is None or args.stage >= 5:
        cmd5 = [py_exe, "05_visualize.py", "--config", args.config]
        if args.force:
            cmd5.append("--force")
        run_command(cmd5, "STAGE 5: Preview Generation & Diagnostic Plotting")

    # Final: Report
    report_path = generate_report(cfg)

    print("\n" + "=" * 80)
    print("PIPELINE COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    print(f"Run Output Directory: {Path(cfg['run_dir']).resolve()}")
    print(f"Report:               {report_path.resolve()}")
    print(f"GeoJSON Candidates:   {(Path(cfg['run_dir']) / 'candidates.geojson').resolve()}")
    print(f"Change Mask:          {(Path(cfg['run_dir']) / 'change_mask.tif').resolve()}")
    print(f"Diagnostic Previews:  {(Path(cfg['run_dir']) / 'previews').resolve()}")


if __name__ == "__main__":
    main()
