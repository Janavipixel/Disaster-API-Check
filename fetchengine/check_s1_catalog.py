
import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)
CATALOG_URL = "https://sh.dataspace.copernicus.eu/catalog/v1/search"

BBOX = [80.85, 26.75, 81.05, 26.95]
TARGET_DATES = ["2026-09-29", "2026-10-04"]


def get_token():
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["CDSE_CLIENT_ID"],
            "client_secret": os.environ["CDSE_CLIENT_SECRET"],
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def search_window(token, target_date, days=3):
    target = datetime.strptime(
        target_date, "%Y-%m-%d"
    ).replace(tzinfo=timezone.utc)

    start = target - timedelta(days=days)
    end = target + timedelta(days=days + 1)

    payload = {
        "bbox": BBOX,
        "datetime": (
            f"{start:%Y-%m-%dT%H:%M:%SZ}/"
            f"{end:%Y-%m-%dT%H:%M:%SZ}"
        ),
        "collections": ["sentinel-1-grd"],
        "limit": 100,
    }

    response = requests.post(
        CATALOG_URL,
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    response.raise_for_status()

    features = response.json().get("features", [])

    print(f"\n{'=' * 75}")
    print(f"Target date: {target_date}")
    print(f"Search range: {payload['datetime']}")
    print(f"Results: {len(features)}")

    scenes = []

    for item in features:
        p = item.get("properties", {})
        polarizations = p.get("sar:polarizations", [])

        # Some responses use a different property name.
        if not polarizations:
            polarizations = p.get("s1:polarization", [])

        scene = {
            "id": item.get("id"),
            "datetime": p.get("datetime"),
            "orbit": p.get("sat:orbit_state"),
            "relative_orbit": p.get("sat:relative_orbit"),
            "mode": p.get("sar:instrument_mode"),
            "polarizations": polarizations,
        }
        scenes.append(scene)

    scenes.sort(key=lambda s: s.get("datetime") or "")

    for scene in scenes:
        print(f"\nID: {scene['id']}")
        print(f"  Acquisition: {scene['datetime']}")
        print(f"  Orbit: {scene['orbit']}")
        print(f"  Relative orbit: {scene['relative_orbit']}")
        print(f"  Mode: {scene['mode']}")
        print(f"  Polarizations: {scene['polarizations']}")

    return scenes


if __name__ == "__main__":
    token = get_token()
    all_scenes = []

    for target in TARGET_DATES:
        all_scenes.extend(search_window(token, target, days=3))

    print("\n" + "=" * 75)
    print("POTENTIAL MATCHES: DESCENDING, RELATIVE ORBIT 92, IW, VV/VH")

    for scene in all_scenes:
        pols = {str(p).upper() for p in scene["polarizations"]}
        if (
            str(scene["orbit"]).lower() == "descending"
            and scene["relative_orbit"] == 92
            and str(scene["mode"]).upper() == "IW"
            and {"VV", "VH"}.issubset(pols)
        ):
            print(scene["datetime"], "|", scene["id"])
