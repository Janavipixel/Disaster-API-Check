"""
pipeline_utils.py: Shared utilities for generic Sentinel-1 disaster change detection.
Handles configuration loading, UTM projections, CDSE authentication, and GeoTIFF I/O.
"""

import os
import math
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import requests
import yaml
from dotenv import load_dotenv
from rasterio.warp import transform_bounds

# Load environment variables from project .env or workspace .env
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)
PROCESS_URL = "https://sh.dataspace.copernicus.eu/process/v1"
CATALOG_URL = "https://sh.dataspace.copernicus.eu/catalog/v1/search"


def get_cdse_token() -> str:
    """Authenticate with CDSE OAuth2 client credentials."""
    client_id = os.getenv("CDSE_CLIENT_ID")
    client_secret = os.getenv("CDSE_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            "Missing CDSE_CLIENT_ID or CDSE_CLIENT_SECRET in .env file. "
            "Please configure your Copernicus Data Space credentials."
        )

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"CDSE authentication failed: HTTP {response.status_code}\n"
            f"{response.text[:500]}"
        )

    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("CDSE did not return an access token.")
    return token


def compute_bbox_from_center(
    center_lat: float, center_lon: float, size_km: float
) -> Tuple[float, float, float, float]:
    """
    Compute a [west, south, east, north] bounding box in EPSG:4326
    centered around (center_lat, center_lon) spanning size_km x size_km.
    """
    half_km = size_km / 2.0
    # Approximate 1 degree latitude = 110.574 km
    d_lat = half_km / 110.574
    # Approximate 1 degree longitude = 111.320 km * cos(lat)
    rad_lat = math.radians(center_lat)
    cos_lat = math.cos(rad_lat)
    if cos_lat < 1e-4:
        cos_lat = 1e-4
    d_lon = half_km / (111.320 * cos_lat)

    west = max(-180.0, center_lon - d_lon)
    east = min(180.0, center_lon + d_lon)
    south = max(-90.0, center_lat - d_lat)
    north = min(90.0, center_lat + d_lat)

    return (round(west, 5), round(south, 5), round(east, 5), round(north, 5))


def get_utm_epsg(lat: float, lon: float) -> int:
    """Determine the optimal UTM EPSG code for a given WGS84 coordinate."""
    zone = int((lon + 180) / 6) + 1
    if lat >= 0:
        return 32600 + zone
    else:
        return 32700 + zone


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load and normalize YAML configuration file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path.resolve()}")

    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Validate essential fields
    if "name" not in cfg:
        raise ValueError("Config must include a 'name' field (e.g. city or region name).")
    if "event_date" not in cfg:
        raise ValueError("Config must include an 'event_date' field (YYYY-MM-DD).")

    # Resolve bounding box
    if "bbox" in cfg and cfg["bbox"]:
        bbox = [float(x) for x in cfg["bbox"]]
        if len(bbox) != 4:
            raise ValueError("'bbox' must be a list of 4 floats: [west, south, east, north]")
        west, south, east, north = bbox
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError(f"Invalid bbox coordinates: {bbox}")
        cfg["bbox"] = bbox
        cfg["center_lon"] = round((west + east) / 2.0, 5)
        cfg["center_lat"] = round((south + north) / 2.0, 5)
    elif "center_lat" in cfg and "center_lon" in cfg:
        size_km = float(cfg.get("size_km", 30.0))
        lat = float(cfg["center_lat"])
        lon = float(cfg["center_lon"])
        cfg["bbox"] = list(compute_bbox_from_center(lat, lon, size_km))
        cfg["size_km"] = size_km
    else:
        raise ValueError("Config must specify either 'bbox' or ('center_lat', 'center_lon', 'size_km').")

    # Set default values
    cfg.setdefault("pre_window_days", 21)
    cfg.setdefault("post_window_days", 21)
    cfg.setdefault("resolution_m", 20.0)
    cfg.setdefault("min_aoi_coverage_pct", 95.0)
    cfg.setdefault("min_valid_pixel_pct", 90.0)
    cfg.setdefault("min_area_m2", 2000.0)
    cfg.setdefault("threshold_method", "adaptive_std")  # 'adaptive_std' or 'otsu'
    cfg.setdefault("k_std", 1.5)

    # Compute UTM EPSG
    utm_epsg = get_utm_epsg(cfg["center_lat"], cfg["center_lon"])
    cfg["utm_epsg"] = utm_epsg

    # Determine run output directory: runs/<name>_<event_date>
    run_dir = Path("runs") / f"{cfg['name'].lower()}_{cfg['event_date']}"
    cfg["run_dir"] = str(run_dir)
    cfg["data_dir"] = str(run_dir / "data")
    cfg["previews_dir"] = str(run_dir / "previews")

    # Create directories
    (run_dir / "data").mkdir(parents=True, exist_ok=True)
    (run_dir / "previews").mkdir(parents=True, exist_ok=True)

    return cfg


def get_utm_bounds(bbox_wgs84: Tuple[float, float, float, float], utm_epsg: int) -> Tuple[float, float, float, float]:
    """Transform WGS84 bbox [west, south, east, north] to UTM metric bounds [min_x, min_y, max_x, max_y]."""
    west, south, east, north = bbox_wgs84
    min_x, min_y, max_x, max_y = transform_bounds("EPSG:4326", f"EPSG:{utm_epsg}", west, south, east, north)
    return (round(min_x, 2), round(min_y, 2), round(max_x, 2), round(max_y, 2))


def calculate_grid_size(
    utm_bounds: Tuple[float, float, float, float],
    resolution_m: float,
    max_dimension: int = 2500
) -> Tuple[int, int, float]:
    """
    Calculate pixel width and height for UTM bounds at requested resolution.
    Coarsens resolution automatically if dimensions exceed max_dimension.
    Returns: (width_px, height_px, effective_resolution_m)
    """
    min_x, min_y, max_x, max_y = utm_bounds
    width_m = max_x - min_x
    height_m = max_y - min_y

    raw_width = max(1, round(width_m / resolution_m))
    raw_height = max(1, round(height_m / resolution_m))

    scale = min(1.0, float(max_dimension) / max(raw_width, raw_height))
    effective_res = resolution_m / scale

    final_width = max(1, round(width_m / effective_res))
    final_height = max(1, round(height_m / effective_res))

    return final_width, final_height, round(effective_res, 2)
