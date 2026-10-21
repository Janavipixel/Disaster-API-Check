"""
01_catalog.py: Stage 1 - Query CDSE STAC Catalogue and rank Sentinel-1 candidate pairs.
Computes AOI polygon footprint intersection coverage percentage (catching swath clipping issues).
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List

import requests
from shapely.geometry import shape, box

from pipeline_utils import load_config, get_cdse_token, CATALOG_URL


def query_catalog(token: str, bbox: List[float], start_iso: str, end_iso: str) -> List[Dict[str, Any]]:
    """Query CDSE STAC search API for Sentinel-1 GRD products."""
    payload = {
        "bbox": bbox,
        "datetime": f"{start_iso}/{end_iso}",
        "collections": ["sentinel-1-grd"],
        "limit": 100,
    }

    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(CATALOG_URL, json=payload, headers=headers, timeout=120)

    if not response.ok:
        raise RuntimeError(
            f"Catalogue query failed: HTTP {response.status_code}\n{response.text[:500]}"
        )

    return response.json().get("features", [])


def parse_scene(feature: Dict[str, Any], aoi_poly) -> Dict[str, Any]:
    """Extract metadata and compute AOI footprint coverage percentage for a scene."""
    props = feature.get("properties", {})
    geom = feature.get("geometry", {})

    # Compute intersection area percentage
    coverage_pct = 0.0
    if geom and aoi_poly:
        try:
            scene_shape = shape(geom)
            if scene_shape.is_valid:
                inter = aoi_poly.intersection(scene_shape)
                coverage_pct = (inter.area / aoi_poly.area) * 100.0
        except Exception:
            coverage_pct = 0.0

    # Polarizations check
    pols = props.get("sar:polarizations", [])
    if not pols:
        pols = props.get("s1:polarization", [])
    pols = [str(p).upper() for p in pols]

    dt_str = props.get("datetime")
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")) if dt_str else None

    return {
        "id": feature.get("id"),
        "datetime": dt_str,
        "dt": dt,
        "orbit_direction": props.get("sat:orbit_state", "").upper(),
        "relative_orbit": props.get("sat:relative_orbit"),
        "instrument_mode": props.get("sar:instrument_mode", "").upper(),
        "polarizations": pols,
        "coverage_pct": round(coverage_pct, 2),
        "bbox": feature.get("bbox"),
    }


def find_candidates(cfg: Dict[str, Any], token: str) -> Dict[str, Any]:
    """Search, filter, group, and rank pre/post candidate acquisition pairs."""
    event_date_str = cfg["event_date"]
    event_dt = datetime.strptime(event_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    pre_start_dt = event_dt - timedelta(days=cfg["pre_window_days"])
    post_end_dt = event_dt + timedelta(days=cfg["post_window_days"])

    bbox = cfg["bbox"]
    aoi_poly = box(*bbox)

    print("=" * 70)
    print("STAGE 1: CDSE CATALOGUE SEARCH & AOI COVERAGE CHECK")
    print("=" * 70)
    print(f"AOI Name:        {cfg['name']}")
    print(f"BBox (WGS84):    {bbox}")
    print(f"Event Date:      {event_date_str}")
    print(f"Search Window:   {pre_start_dt.strftime('%Y-%m-%d')} to {post_end_dt.strftime('%Y-%m-%d')}")
    print(f"Min Coverage %:  {cfg['min_aoi_coverage_pct']}%")

    features = query_catalog(
        token=token,
        bbox=bbox,
        start_iso=f"{pre_start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        end_iso=f"{post_end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}",
    )
    print(f"\nTotal raw catalogue scenes intersecting AOI: {len(features)}")

    parsed_scenes = [parse_scene(f, aoi_poly) for f in features]

    # Filter to IW mode and VV+VH polarizations
    usable_scenes = []
    all_swath_stats = []
    for s in parsed_scenes:
        has_pols = {"VV", "VH"}.issubset(set(s["polarizations"]))
        is_iw = s["instrument_mode"] == "IW"
        all_swath_stats.append(s)
        if has_pols and is_iw:
            # Filter optional orbit direction or relative orbit from config
            if cfg.get("orbit_direction") and s["orbit_direction"] != cfg["orbit_direction"].upper():
                continue
            if cfg.get("relative_orbit") and s["relative_orbit"] != cfg["relative_orbit"]:
                continue
            usable_scenes.append(s)

    # Partition into pre and post
    pre_scenes = [s for s in usable_scenes if s["dt"] and s["dt"] < event_dt]
    post_scenes = [s for s in usable_scenes if s["dt"] and s["dt"] >= event_dt]

    print(f"Usable IW VV/VH scenes: {len(usable_scenes)} (Pre: {len(pre_scenes)}, Post: {len(post_scenes)})")

    # Group by (relative_orbit, orbit_direction)
    min_cov = cfg["min_aoi_coverage_pct"]
    groups = {}
    for s in usable_scenes:
        key = (s["relative_orbit"], s["orbit_direction"])
        groups.setdefault(key, {"pre": [], "post": []})
        if s["dt"] < event_dt:
            groups[key]["pre"].append(s)
        else:
            groups[key]["post"].append(s)

    # Form and score candidate pairs
    candidate_pairs = []
    rejected_groups = []

    for (rel_orbit, orbit_dir), group in groups.items():
        pre_valid = [s for s in group["pre"] if s["coverage_pct"] >= min_cov]
        post_valid = [s for s in group["post"] if s["coverage_pct"] >= min_cov]

        if not pre_valid or not post_valid:
            max_pre_cov = max([s["coverage_pct"] for s in group["pre"]], default=0.0)
            max_post_cov = max([s["coverage_pct"] for s in group["post"]], default=0.0)
            rejected_groups.append({
                "relative_orbit": rel_orbit,
                "orbit_direction": orbit_dir,
                "pre_count": len(group["pre"]),
                "post_count": len(group["post"]),
                "max_pre_coverage": max_pre_cov,
                "max_post_coverage": max_post_cov,
                "reason": (
                    f"Coverage below {min_cov}% (Pre max: {max_pre_cov}%, Post max: {max_post_cov}%)"
                    if (group["pre"] and group["post"])
                    else "Missing pre or post acquisition in window"
                )
            })
            continue

        # Form pairs from valid scenes (sort by closest to event date)
        pre_valid.sort(key=lambda s: abs((event_dt - s["dt"]).total_seconds()))
        post_valid.sort(key=lambda s: abs((s["dt"] - event_dt).total_seconds()))

        for pre_scene in pre_valid:
            for post_scene in post_valid:
                pre_gap = abs((event_dt - pre_scene["dt"]).total_seconds()) / 86400.0
                post_gap = abs((post_scene["dt"] - event_dt).total_seconds()) / 86400.0
                total_gap = pre_gap + post_gap
                pair_cov = min(pre_scene["coverage_pct"], post_scene["coverage_pct"])

                candidate_pairs.append({
                    "relative_orbit": rel_orbit,
                    "orbit_direction": orbit_dir,
                    "pre_scene": {
                        "id": pre_scene["id"],
                        "datetime": pre_scene["datetime"],
                        "coverage_pct": pre_scene["coverage_pct"],
                        "gap_days": round(pre_gap, 2),
                    },
                    "post_scene": {
                        "id": post_scene["id"],
                        "datetime": post_scene["datetime"],
                        "coverage_pct": post_scene["coverage_pct"],
                        "gap_days": round(post_gap, 2),
                    },
                    "min_coverage_pct": pair_cov,
                    "total_gap_days": round(total_gap, 2),
                })

    # Sort candidate pairs: higher min_coverage first, then shorter gap to event
    candidate_pairs.sort(
        key=lambda p: (-p["min_coverage_pct"], p["total_gap_days"])
    )

    # Assign pair IDs
    for idx, p in enumerate(candidate_pairs, start=1):
        p["pair_id"] = f"PAIR_{idx:02d}"

    return {
        "candidate_pairs": candidate_pairs,
        "rejected_groups": rejected_groups,
        "all_scenes": [
            {
                "id": s["id"],
                "datetime": s["datetime"],
                "orbit_direction": s["orbit_direction"],
                "relative_orbit": s["relative_orbit"],
                "coverage_pct": s["coverage_pct"],
            }
            for s in all_swath_stats
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="CDSE Sentinel-1 Catalogue Search & AOI Coverage Ranking")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--pick", default=None, help="Specific candidate pair ID or 1-based index to select")
    args = parser.parse_args()

    cfg = load_config(args.config)
    token = get_cdse_token()

    results = find_candidates(cfg, token)
    candidate_pairs = results["candidate_pairs"]
    rejected_groups = results["rejected_groups"]

    run_dir = Path(cfg["run_dir"])
    candidates_file = run_dir / "candidates.json"
    candidates_file.write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Display results
    if not candidate_pairs:
        print("\n" + "!" * 70)
        print("ERROR: No suitable Sentinel-1 candidate pairs found with adequate coverage!")
        print("!" * 70)
        if rejected_groups:
            print("\nOrbits inspected but rejected:")
            for r in rejected_groups:
                print(
                    f"  - Orbit {r['relative_orbit']} ({r['orbit_direction']}): "
                    f"Pre: {r['pre_count']}, Post: {r['post_count']}, "
                    f"Coverage: Pre={r['max_pre_coverage']}%, Post={r['max_post_coverage']}% -> {r['reason']}"
                )
        print(f"\nRecommendations:")
        print(f"  1. Increase 'pre_window_days' or 'post_window_days' in {args.config}")
        print(f"  2. Adjust or shift the AOI bounding box/center point")
        print(f"  3. Check CDSE catalogue availability for the selected event date.")
        sys.exit(1)

    print(f"\n{'=' * 75}")
    print(f"VALID CANDIDATE PAIRS (>= {cfg['min_aoi_coverage_pct']}% AOI coverage):")
    print(f"{'=' * 75}")
    header = f"{'Rank':<5} {'Pair ID':<8} {'RelOrb':<7} {'Orbit':<11} {'Pre-Date':<17} {'Post-Date':<17} {'Min Cov':<9} {'Gap (d)':<7}"
    print(header)
    print("-" * 85)

    for idx, p in enumerate(candidate_pairs, start=1):
        pre_d = p["pre_scene"]["datetime"][:16].replace("T", " ")
        post_d = p["post_scene"]["datetime"][:16].replace("T", " ")
        print(
            f"{idx:<5} {p['pair_id']:<8} {p['relative_orbit']:<7} {p['orbit_direction']:<11} "
            f"{pre_d:<17} {post_d:<17} {p['min_coverage_pct']:<8.1f}% {p['total_gap_days']:<7.1f}"
        )

    # Determine selected pair
    selected_pair = None
    if args.pick:
        pick_str = str(args.pick).strip().upper()
        for idx, p in enumerate(candidate_pairs, start=1):
            if pick_str in (p["pair_id"], str(idx)):
                selected_pair = p
                print(f"\nUser override: Selected {p['pair_id']} (Rank {idx})")
                break
        if not selected_pair:
            print(f"\nWARNING: Pick '{args.pick}' not found. Defaulting to Rank 1.")
            selected_pair = candidate_pairs[0]
    else:
        selected_pair = candidate_pairs[0]
        print(f"\nAuto-selected Best Candidate: {selected_pair['pair_id']} (Relative Orbit {selected_pair['relative_orbit']}, {selected_pair['orbit_direction']})")

    # Update metadata.json
    metadata_file = run_dir / "metadata.json"
    metadata = {}
    if metadata_file.exists():
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}

    metadata["config"] = cfg
    metadata["stage_1_catalog"] = {
        "status": "COMPLETED",
        "selected_pair": selected_pair,
        "total_candidates": len(candidate_pairs),
        "candidates_file": str(candidates_file),
    }

    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Candidates saved to: {candidates_file}")
    print(f"Metadata updated:    {metadata_file}")


if __name__ == "__main__":
    main()
