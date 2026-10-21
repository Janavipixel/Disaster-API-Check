"""
Satellite Evidence Adapter.

Converts Copernicus Sentinel-1 SAR change-detection outputs (from the teammate's
satellite processing pipeline or demo fixtures) into structured, verifiable
evidence for the RAG/LLM pipeline.

Implements rigorous matching between disaster reports and satellite observations
using:
  1. Event ID matching
  2. Geographic / bounding box spatial overlap
  3. Pre/post acquisition temporal window overlap

Prevents treating unverified operational context as verified instrument measurements.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SatelliteEvidence:
    """
    Structured, verified satellite observation record produced from
    Copernicus Sentinel-1 SAR change detection.
    """
    event_id: str
    event_name: str
    hazard_type: str
    sensor: str                             # e.g. "Sentinel-1A"
    polarisation: str                        # e.g. "VV"
    pass_direction: str                      # e.g. "Ascending"
    pre_event_date: str                     # e.g. "2024-05-28"
    post_event_date: str                    # e.g. "2024-06-21"
    aoi_bbox: Optional[List[float]] = None  # [min_lon, min_lat, max_lon, max_lat]
    aoi_center: Optional[List[float]] = None # [lat, lon]
    total_flood_area_km2: Optional[float] = None
    new_flood_area_km2: Optional[float] = None
    change_threshold_db: Optional[float] = None
    affected_roads_km: Optional[float] = None
    affected_bridges: Optional[int] = None
    affected_agri_km2: Optional[float] = None
    estimated_population_affected: Optional[int] = None
    land_cover_breakdown: List[Dict[str, Any]] = field(default_factory=list)
    priority_zones: List[Dict[str, Any]] = field(default_factory=list)
    infrastructure_impacts: List[Dict[str, Any]] = field(default_factory=list)
    backscatter_progression: List[Dict[str, Any]] = field(default_factory=list)
    confidence_notes: Optional[str] = None
    pre_scene_id: Optional[str] = None
    post_scene_id: Optional[str] = None
    verification_source: str = "Copernicus Sentinel-1 SAR Pipeline"
    is_demo: bool = False

    def to_context_string(self) -> str:
        """
        Convert verified satellite observations into a structured Markdown block
        for LLM prompt grounding. Distinguishes verified instrument observations
        from unverified demo or simulated datasets.
        """
        is_unverified_demo = (
            self.is_demo
            or "demo" in self.verification_source.lower()
            or "simulat" in self.verification_source.lower()
            or "mock" in self.verification_source.lower()
        )
        header = (
            "## Satellite Observations [DEMO / SIMULATED DATA - UNVERIFIED]"
            if is_unverified_demo
            else "## Verified Copernicus Satellite Observations (Sentinel-1 SAR)"
        )
        provenance_str = (
            f"SIMULATED / DEMO DATASET ({self.verification_source}) — NOT independently verified instrument observations"
            if is_unverified_demo
            else f"Level-1 GRD Terrain Corrected (RTC) via {self.verification_source}"
        )

        lines = [
            header,
            f"- **Event Name**: {self.event_name} (ID: {self.event_id})",
            f"- **Sensor & Mode**: {self.sensor} ({self.polarisation} polarisation, {self.pass_direction} pass)",
            f"- **Observation Window**: Pre-event baseline: {self.pre_event_date} | Post-event observation: {self.post_event_date}",
            f"- **Instrument Provenance**: {provenance_str}",
        ]
        if self.pre_scene_id or self.post_scene_id:
            scenes = f"Pre: {self.pre_scene_id or 'N/A'} | Post: {self.post_scene_id or 'N/A'}"
            lines.append(f"- **Scene Identifiers**: {scenes}")

        if self.total_flood_area_km2 is not None:
            thresh_str = f" (Threshold: {self.change_threshold_db} dB)" if self.change_threshold_db else ""
            lines.append(
                f"- **Delineated Inundation**: Total: {self.total_flood_area_km2:.1f} km² "
                f"| Newly Flooded: {self.new_flood_area_km2 or 0.0:.1f} km²{thresh_str}"
            )

        if self.estimated_population_affected or self.affected_roads_km or self.affected_agri_km2:
            impact_parts = []
            if self.estimated_population_affected:
                impact_parts.append(f"~{self.estimated_population_affected:,} people in inundation zone")
            if self.affected_roads_km:
                bridge_str = f" ({self.affected_bridges} bridges)" if self.affected_bridges else ""
                impact_parts.append(f"{self.affected_roads_km:.1f} km road flooded{bridge_str}")
            if self.affected_agri_km2:
                impact_parts.append(f"{self.affected_agri_km2:.1f} km² cropland inundated")
            lines.append(f"- **Satellite-Observed Ground Impact**: {'; '.join(impact_parts)}")

        if self.priority_zones:
            lines.append("- **Critical Ground Priority Zones (Ranked Field Targets)**:")
            for pz in self.priority_zones[:3]:
                coords = f" [coords: {pz.get('coordinates')}]" if pz.get("coordinates") else ""
                lines.append(f"  * Rank {pz.get('rank', '-')}: {pz.get('label')}{coords} — {pz.get('reason')}")

        if self.confidence_notes:
            lines.append(f"- **Data Quality & Limitations**: {self.confidence_notes}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API responses."""
        return {
            "event_id": self.event_id,
            "event_name": self.event_name,
            "hazard_type": self.hazard_type,
            "sensor": self.sensor,
            "polarisation": self.polarisation,
            "pass_direction": self.pass_direction,
            "pre_event_date": self.pre_event_date,
            "post_event_date": self.post_event_date,
            "aoi_bbox": self.aoi_bbox,
            "aoi_center": self.aoi_center,
            "total_flood_area_km2": self.total_flood_area_km2,
            "new_flood_area_km2": self.new_flood_area_km2,
            "change_threshold_db": self.change_threshold_db,
            "affected_roads_km": self.affected_roads_km,
            "affected_bridges": self.affected_bridges,
            "affected_agri_km2": self.affected_agri_km2,
            "estimated_population_affected": self.estimated_population_affected,
            "priority_zones": self.priority_zones,
            "confidence_notes": self.confidence_notes,
            "verification_source": self.verification_source,
            "is_demo": self.is_demo,
        }


class SatelliteEvidenceAdapter:
    """
    Adapts Copernicus satellite outputs into structured `SatelliteEvidence`.
    Validates and correlates satellite observations with disaster events.
    """

    @classmethod
    def from_copernicus_output(
        cls,
        event: Dict[str, Any],
        analysis: Optional[Dict[str, Any]] = None,
        impact: Optional[Dict[str, Any]] = None,
        priority_zones: Optional[Dict[str, Any]] = None,
        infrastructure: Optional[Dict[str, Any]] = None,
        timeseries: Optional[List[Dict[str, Any]]] = None,
        images: Optional[Dict[str, Any]] = None,
        verification_source: Optional[str] = None,
    ) -> SatelliteEvidence:
        """
        Build a verified SatelliteEvidence object from raw Copernicus / SAR outputs.
        Distinguishes independently verified instrument runs from simulated/demo data.
        """
        aoi = event.get("aoi", {})
        analysis = analysis or {}
        impact = impact or {}
        images = images or {}

        # Detect if dataset is marked as demo/simulated
        is_demo = bool(
            event.get("isDemo")
            or event.get("is_demo")
            or event.get("status") == "demo"
            or "demo" in str(event.get("id", "")).lower()
            or "demo" in str(event.get("name", "")).lower()
            or analysis.get("isDemo")
            or "demo" in str(analysis.get("algorithmVersion", "")).lower()
        )

        v_source = (
            verification_source
            or analysis.get("verificationSource")
            or ("Demo / Simulated SAR Dataset (Unverified)" if is_demo else "Copernicus Sentinel-1 SAR Pipeline")
        )

        # Parse priority zones features
        pz_list = []
        if priority_zones and isinstance(priority_zones, dict):
            features = priority_zones.get("features", [])
            for f in features:
                props = f.get("properties", {})
                geom = f.get("geometry", {})
                pz_list.append({
                    "id": props.get("id"),
                    "rank": props.get("rank"),
                    "priority": props.get("priority"),
                    "label": props.get("label"),
                    "reason": props.get("reason"),
                    "pop_estimate": props.get("popEstimate"),
                    "coordinates": geom.get("coordinates"),
                })

        # Parse infrastructure features
        infra_list = []
        if infrastructure and isinstance(infrastructure, dict):
            for f in infrastructure.get("features", []):
                props = f.get("properties", {})
                geom = f.get("geometry", {})
                infra_list.append({
                    "name": props.get("name"),
                    "type": props.get("type"),
                    "affected_km": props.get("affectedKm"),
                    "status": props.get("status"),
                    "coordinates": geom.get("coordinates"),
                })

        pre_meta = images.get("pre", {})
        post_meta = images.get("post", {})

        return SatelliteEvidence(
            event_id=event.get("id", "unknown-event"),
            event_name=event.get("name", "Unnamed Satellite Observation"),
            hazard_type=event.get("type", "flood"),
            sensor=event.get("sensor") or post_meta.get("sensor", "Sentinel-1"),
            polarisation=event.get("polarisation") or post_meta.get("polarisation", "VV"),
            pass_direction=event.get("passDirection") or post_meta.get("orbit", "Unknown"),
            pre_event_date=event.get("preDate") or pre_meta.get("date", ""),
            post_event_date=event.get("postDate") or post_meta.get("date", ""),
            aoi_bbox=aoi.get("bbox"),
            aoi_center=aoi.get("center"),
            total_flood_area_km2=impact.get("totalFloodAreaKm2"),
            new_flood_area_km2=impact.get("newFloodAreaKm2"),
            change_threshold_db=analysis.get("changeThresholdDb"),
            affected_roads_km=impact.get("affectedRoadKm"),
            affected_bridges=impact.get("affectedBridgeCount"),
            affected_agri_km2=impact.get("affectedAgriKm2"),
            estimated_population_affected=impact.get("estimatedPopulationAffected"),
            land_cover_breakdown=impact.get("breakdown", []),
            priority_zones=pz_list,
            infrastructure_impacts=infra_list,
            backscatter_progression=timeseries or [],
            confidence_notes=analysis.get("confidenceNotes"),
            pre_scene_id=pre_meta.get("sourceId"),
            post_scene_id=post_meta.get("sourceId"),
            verification_source=v_source,
            is_demo=is_demo,
        )

    @classmethod
    def match_satellite_with_event(
        cls,
        satellite: SatelliteEvidence,
        disaster_event: Dict[str, Any],
    ) -> Tuple[bool, str, float]:
        """
        Verify that a satellite observation matches a disaster event using:
          1. Event ID match
          2. Spatial bounding box / coordinate match
          3. Temporal acquisition window overlap

        Returns
        -------
        Tuple[bool, str, float]
            (is_matched, explanation, confidence_score)
        """
        match_score = 0.0
        reasons = []

        # 1. Event ID match
        target_id = str(disaster_event.get("event_id") or disaster_event.get("id") or "").lower()
        sat_id = satellite.event_id.lower()
        if target_id and (target_id == sat_id or target_id in sat_id or sat_id in target_id):
            match_score += 0.50
            reasons.append(f"Event ID matches ({satellite.event_id})")

        # 2. Hazard type match
        ev_hazard = str(disaster_event.get("hazard_types") or disaster_event.get("hazard") or "").lower()
        if ev_hazard and (satellite.hazard_type.lower() in ev_hazard or ev_hazard in satellite.hazard_type.lower()):
            match_score += 0.15
            reasons.append(f"Hazard type aligned ({satellite.hazard_type})")

        # 3. Spatial location match
        coords = disaster_event.get("coordinates")
        region = str(disaster_event.get("region") or disaster_event.get("location") or "").lower()
        sat_name = satellite.event_name.lower()

        if coords and isinstance(coords, (list, tuple)) and len(coords) == 2:
            lat, lon = coords[0], coords[1]
            if satellite.aoi_bbox and len(satellite.aoi_bbox) == 4:
                min_lon, min_lat, max_lon, max_lat = satellite.aoi_bbox
                # Buffer slightly (0.2 degrees)
                if (min_lon - 0.2 <= lon <= max_lon + 0.2) and (min_lat - 0.2 <= lat <= max_lat + 0.2):
                    match_score += 0.35
                    reasons.append("Coordinates fall inside satellite AOI bounding box")
                else:
                    return (
                        False,
                        f"Spatial mismatch: event coordinates [{lat}, {lon}] fall outside satellite AOI bbox {satellite.aoi_bbox}",
                        0.0,
                    )
        elif region and (region in sat_name or any(part.strip() in sat_name for part in region.split(","))):
            match_score += 0.25
            reasons.append(f"Region '{region}' matches satellite AOI name '{satellite.event_name}'")

        # 4. Temporal window match
        ev_date_str = str(disaster_event.get("event_date") or disaster_event.get("date") or "")
        if ev_date_str and len(ev_date_str) >= 10:
            try:
                ev_date = datetime.strptime(ev_date_str[:10], "%Y-%m-%d").date()
                pre_date = datetime.strptime(satellite.pre_event_date[:10], "%Y-%m-%d").date()
                post_date = datetime.strptime(satellite.post_event_date[:10], "%Y-%m-%d").date()

                if pre_date <= ev_date <= post_date:
                    match_score += 0.20
                    reasons.append(f"Event date {ev_date} is within satellite window [{pre_date} to {post_date}]")
                elif abs((ev_date - post_date).days) <= 14:
                    match_score += 0.10
                    reasons.append(f"Event date {ev_date} is near satellite post-pass {post_date}")
                else:
                    return (
                        False,
                        f"Temporal mismatch: event date {ev_date} is outside satellite acquisition window [{pre_date} to {post_date}]",
                        0.0,
                    )
            except ValueError:
                pass

        if match_score >= 0.35:
            return True, f"Verified match: {', '.join(reasons)}", round(min(1.0, match_score), 2)

        return False, "Insufficient spatial or identifier overlap to match satellite evidence.", round(match_score, 2)
