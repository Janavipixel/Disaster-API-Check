#!/usr/bin/env python3
"""
CLI Script: Build the vector index from scraped JSONL documents.

Usage:
    python scripts/build_index.py
    python scripts/build_index.py --input data/raw_documents.jsonl
    python scripts/build_index.py --create-fixtures   # create offline test data
    python scripts/build_index.py --clear             # wipe and rebuild the index

This script must be run from the project root directory.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Fix Windows console encoding for Unicode/emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("build_index")


def load_jsonl(path: Path):
    """Load DisasterDocument objects from a JSONL file."""
    from processor.validator import DisasterDocument

    docs = []
    errors = 0
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                doc = DisasterDocument(**data)
                docs.append(doc)
            except Exception as e:
                errors += 1
                logger.warning("Line %d: skipped invalid record — %s", i, e)
    logger.info("Loaded %d valid documents (%d errors) from %s", len(docs), errors, path)
    return docs


def create_fixtures():
    """Generate offline test fixture documents."""
    from datetime import datetime, timezone

    fixtures = [
        {
            "document_id": "doc_fixture_copernicus_001",
            "title": "Sentinel-1 SAR Data Access — Copernicus Data Space",
            "source_url": "https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/OGC/WCS.html",
            "source_type": "official_documentation",
            "publisher": "Copernicus / ESA",
            "hazard_types": ["flood"],
            "region": "Europe",
            "coordinates": None,
            "event_date": None,
            "content_type": "technical_documentation",
            "published_at": "2024-01-15",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "content": (
                "Sentinel-1 is a C-band SAR (Synthetic Aperture Radar) satellite constellation operated by ESA "
                "as part of the Copernicus programme. It provides all-weather, day-and-night radar imaging, "
                "making it exceptionally valuable for disaster monitoring including floods, earthquakes, and landslides.\n\n"
                "For flood mapping, Sentinel-1 backscatter values over flooded areas are significantly lower than "
                "over dry land due to specular reflection of radar signals off smooth water surfaces. "
                "Change detection between pre-event and post-event SAR images allows automated delineation "
                "of flood extents with high spatial resolution (10 m GRD products).\n\n"
                "The Copernicus Data Space Ecosystem provides free and open access to Sentinel-1 data through "
                "multiple APIs including OData, STAC, and SentinelHub. Authentication uses OAuth2 client credentials. "
                "Data is available in IW (Interferometric Wide) swath mode for most land applications, "
                "with Level-1 GRD and SLC products suitable for flood mapping and change detection respectively."
            ),
            "content_hash": "",
            "verification_status": "fixture",
            "tags": ["SAR", "Sentinel-1", "satellite", "data-access", "flood-mapping"],
            "language": "en",
            "word_count": 0,
        },
        {
            "document_id": "doc_fixture_gdacs_flood_001",
            "title": "GDACS Alert: Major Flood Event — Bangladesh",
            "source_url": "https://www.gdacs.org/report.aspx?eventid=1234567&episodeid=1",
            "source_type": "disaster_report",
            "publisher": "GDACS",
            "hazard_types": ["flood"],
            "region": "Bangladesh",
            "coordinates": [23.685, 90.356],
            "event_date": "2024-06-15",
            "content_type": "disaster_alert",
            "published_at": "2024-06-16",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "content": (
                "GDACS ALERT — RED LEVEL: Major Flood in Bangladesh\n\n"
                "A severe monsoon flood event is affecting northeastern Bangladesh, particularly "
                "the Sylhet and Sunamganj districts. The Surma and Kushiyara rivers have exceeded "
                "danger levels by 2-3 metres. Approximately 4 million people are estimated to be affected.\n\n"
                "Flash floods triggered by extremely heavy rainfall (>300 mm in 48 hours) have inundated "
                "over 800,000 hectares of agricultural land. Road networks in the affected districts are "
                "severely disrupted. Emergency response operations are ongoing by the Bangladesh Disaster "
                "Management Authority (BDMA) in coordination with UN agencies.\n\n"
                "Satellite change detection using Sentinel-1 SAR imagery (pre-event: June 1, post-event: June 16) "
                "shows a flood footprint of approximately 180,000 hectares in the Sylhet division. "
                "The Copernicus Emergency Management Service has been activated."
            ),
            "content_hash": "",
            "verification_status": "fixture",
            "tags": ["disaster", "flood", "Bangladesh", "SAR"],
            "language": "en",
            "word_count": 0,
        },
        {
            "document_id": "doc_fixture_reliefweb_turkey_001",
            "title": "Turkey-Syria Earthquake 2023 — Humanitarian Response Situation Report",
            "source_url": "https://reliefweb.int/report/turkey/turkey-earthquake-situation-report-no-12",
            "source_type": "disaster_report",
            "publisher": "OCHA",
            "hazard_types": ["earthquake"],
            "region": "Turkey",
            "coordinates": [37.174, 37.031],
            "event_date": "2023-02-06",
            "content_type": "situation_report",
            "published_at": "2023-02-20",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "content": (
                "Situation Report #12 — Turkey-Syria Earthquake Response\n\n"
                "On 6 February 2023, two devastating earthquakes of magnitude Mw 7.8 and Mw 7.5 struck "
                "southeast Turkey and northern Syria, causing widespread destruction across 11 provinces. "
                "The earthquakes are among the deadliest in the region's recorded history.\n\n"
                "Key figures: Over 50,000 confirmed fatalities in Turkey alone. More than 100,000 people injured. "
                "Approximately 13.5 million people affected across both countries. 14 provinces declared "
                "disaster zones in Turkey.\n\n"
                "Satellite imagery analysis: The Copernicus Emergency Management Service activated the "
                "EMSN (Emergency Management Service - Mapping) for affected areas. Sentinel-1 SAR change "
                "detection identified over 12,000 collapsed or heavily damaged structures in Kahramanmaras, "
                "Hatay, and Gaziantep provinces. Coherence change detection highlighted areas of ground "
                "deformation along the East Anatolian Fault.\n\n"
                "Search and rescue operations involved teams from 94 countries. Humanitarian needs include "
                "emergency shelter, water, food, and medical care for an estimated 1.5 million displaced people."
            ),
            "content_hash": "",
            "verification_status": "fixture",
            "tags": ["disaster", "earthquake", "Turkey", "Syria", "satellite"],
            "language": "en",
            "word_count": 0,
        },
        {
            "document_id": "doc_fixture_gee_001",
            "title": "Google Earth Engine — SAR Change Detection Guide",
            "source_url": "https://developers.google.com/earth-engine/guides/sar-basics",
            "source_type": "official_documentation",
            "publisher": "Google",
            "hazard_types": [],
            "region": None,
            "coordinates": None,
            "event_date": None,
            "content_type": "technical_documentation",
            "published_at": "2024-03-10",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "content": (
                "SAR Basics in Google Earth Engine\n\n"
                "Synthetic Aperture Radar (SAR) data in Google Earth Engine is primarily sourced from "
                "the Sentinel-1 mission. The Sentinel-1 GRD (Ground Range Detected) collection is available "
                "as ee.ImageCollection('COPERNICUS/S1_GRD') and includes data from 2014 onwards.\n\n"
                "Key SAR processing concepts for disaster mapping:\n"
                "1. Backscatter change detection: Compare pre- and post-event VV or VH polarisation backscatter. "
                "   Flooded areas show reduced backscatter; building collapse may show increased or changed backscatter.\n"
                "2. Coherence analysis: Phase coherence between two SAR acquisitions drops to near zero over flooded "
                "   or disturbed surfaces, providing a sensitive change indicator.\n"
                "3. Filtering: Lee, Gamma-MAP, or refined Lee filters reduce speckle noise in SAR imagery.\n\n"
                "Example flood mapping workflow in GEE:\n"
                "- Filter Sentinel-1 collection by date, orbit direction (ASCENDING/DESCENDING), and instrument mode (IW).\n"
                "- Select VV polarisation for open water detection.\n"
                "- Apply otsu thresholding on the difference image (post - pre) to classify flood pixels.\n"
                "- Mask permanent water bodies using the JRC Global Surface Water dataset.\n\n"
                "Earth Engine scales analysis across Google's infrastructure, making it suitable for "
                "regional and national-scale flood mapping during active disaster events."
            ),
            "content_hash": "",
            "verification_status": "fixture",
            "tags": ["GEE", "SAR", "Sentinel-1", "flood-mapping", "change-detection"],
            "language": "en",
            "word_count": 0,
        },
        {
            "document_id": "doc_fixture_nasa_001",
            "title": "NASA Earthdata — Disaster Applications and Rapid Response",
            "source_url": "https://www.earthdata.nasa.gov/learn/disasters",
            "source_type": "official_documentation",
            "publisher": "NASA",
            "hazard_types": ["flood", "wildfire", "earthquake"],
            "region": None,
            "coordinates": None,
            "event_date": None,
            "content_type": "technical_documentation",
            "published_at": "2024-02-01",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "content": (
                "NASA Earthdata Disasters Program\n\n"
                "NASA provides near-real-time Earth observation data to support disaster response and recovery. "
                "Key datasets relevant to disaster intelligence include:\n\n"
                "MODIS (Terra/Aqua): Daily global coverage at 250m–1km resolution. FIRMS (Fire Information for "
                "Resource Management System) provides near-real-time active fire detections. "
                "Useful for wildfire monitoring and flood inundation mapping.\n\n"
                "Landsat 8/9: 30-metre multispectral imagery with 16-day revisit. Critical for change detection "
                "over agricultural areas, urban damage assessment, and pre/post disaster comparisons.\n\n"
                "ARIA (Advanced Rapid Imaging and Analysis) Project: Provides processed SAR-based damage proxy maps "
                "within 24-48 hours of major earthquakes and other disasters. Uses Sentinel-1 and ALOS-2 SAR data. "
                "Products include Damage Proxy Maps (DPM) showing likely building damage extent.\n\n"
                "IMERG (Integrated Multi-satellitE Retrievals for GPM): Near-real-time precipitation data at "
                "0.1-degree resolution, updated every 30 minutes. Essential for flood triggering analysis and "
                "rainfall-triggered landslide assessments.\n\n"
                "All NASA Earthdata products are freely available through Earthdata Search. "
                "API access is available through CMR (Common Metadata Repository) and OPeNDAP."
            ),
            "content_hash": "",
            "verification_status": "fixture",
            "tags": ["NASA", "satellite", "disaster", "earth-observation", "flood", "wildfire"],
            "language": "en",
            "word_count": 0,
        },
        {
            "document_id": "doc_fixture_cyclone_001",
            "title": "Cyclone Mocha — Myanmar and Bangladesh Landfall Report",
            "source_url": "https://reliefweb.int/report/myanmar/cyclone-mocha-situation-report-3",
            "source_type": "disaster_report",
            "publisher": "OCHA",
            "hazard_types": ["cyclone"],
            "region": "Myanmar",
            "coordinates": [20.15, 92.9],
            "event_date": "2023-05-14",
            "content_type": "situation_report",
            "published_at": "2023-05-16",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "content": (
                "Cyclone Mocha Situation Report #3 — Myanmar / Bangladesh\n\n"
                "Cyclone Mocha made landfall near Sittwe, Rakhine State, Myanmar on 14 May 2023 "
                "with maximum sustained winds of 209 km/h (Category 4 equivalent), making it one of the "
                "strongest cyclones ever recorded in the Bay of Bengal region.\n\n"
                "Impact summary:\n"
                "- Rakhine State: Approximately 800,000 people affected. Sittwe city sustained catastrophic damage "
                "  with over 80% of structures reported damaged or destroyed. Massive displacement of Rohingya "
                "  communities from IDP camps.\n"
                "- Cox's Bazar, Bangladesh: 300,000 people in Rohingya refugee camps affected by strong winds "
                "  and heavy rainfall. 70,000+ shelters damaged.\n\n"
                "Satellite analysis: Copernicus EMS activated. Sentinel-1 SAR imagery acquired on 15 May showed "
                "extensive inundation along the Kaladan River delta and coastal storm surge flooding extending "
                "10-15 km inland. Damage assessments conducted using Pleiades and WorldView optical imagery "
                "in combination with SAR change detection."
            ),
            "content_hash": "",
            "verification_status": "fixture",
            "tags": ["disaster", "cyclone", "Myanmar", "Bangladesh", "satellite"],
            "language": "en",
            "word_count": 0,
        },
    ]

    fixture_path = Path("data/fixtures/test_documents.jsonl")
    fixture_path.parent.mkdir(parents=True, exist_ok=True)

    from processor.validator import DisasterDocument
    import hashlib

    with fixture_path.open("w", encoding="utf-8") as f:
        for rec in fixtures:
            # Compute content_hash and word_count if missing
            content = rec["content"]
            rec["content_hash"] = hashlib.sha256(content.encode()).hexdigest()
            rec["word_count"] = len(content.split())
            doc = DisasterDocument(**rec)
            f.write(doc.model_dump_json() + "\n")

    logger.info("Created %d fixture documents → %s", len(fixtures), fixture_path)
    return fixture_path


def main():
    parser = argparse.ArgumentParser(
        description="Build ChromaDB vector index from scraped JSONL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        default="data/raw_documents.jsonl",
        help="Input JSONL file (default: data/raw_documents.jsonl)",
    )
    parser.add_argument(
        "--create-fixtures",
        action="store_true",
        help="Create offline test fixture documents and index them",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing vector index before building",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="Target words per chunk (default: 512)",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=64,
        help="Word overlap between chunks (default: 64)",
    )
    parser.add_argument(
        "--persist-dir",
        default="data/chroma_db",
        help="ChromaDB persistence directory (default: data/chroma_db)",
    )
    args = parser.parse_args()

    from rag.chunker import chunk_documents
    from rag.embedder import Embedder
    from rag.vector_store import VectorStore

    input_path = Path(args.input)

    # ── Fixtures mode ─────────────────────────────────────────────────────────
    if args.create_fixtures:
        logger.info("Creating offline fixture documents ...")
        fixture_path = create_fixtures()
        input_path = fixture_path

    if not input_path.exists():
        logger.error(
            "Input file not found: %s\n"
            "Run the scraper first:  python scripts/run_scraper.py\n"
            "Or use fixtures:        python scripts/build_index.py --create-fixtures",
            input_path,
        )
        sys.exit(1)

    # ── Load documents ────────────────────────────────────────────────────────
    docs = load_jsonl(input_path)
    if not docs:
        logger.error("No valid documents found in %s", input_path)
        sys.exit(1)

    # ── Chunk documents ───────────────────────────────────────────────────────
    logger.info("Chunking %d documents (chunk_size=%d, overlap=%d) ...", len(docs), args.chunk_size, args.chunk_overlap)
    chunks = chunk_documents(docs, chunk_size=args.chunk_size, overlap=args.chunk_overlap)
    logger.info("Generated %d chunks", len(chunks))

    # ── Build vector store ────────────────────────────────────────────────────
    embedder = Embedder()
    store = VectorStore(embedder=embedder, persist_dir=args.persist_dir)

    if args.clear:
        logger.warning("Clearing existing index ...")
        store.clear()

    added = store.add_chunks(chunks)
    logger.info(
        "Index built. Total chunks in store: %d  |  Persist dir: %s",
        store.count(),
        args.persist_dir,
    )


if __name__ == "__main__":
    main()
