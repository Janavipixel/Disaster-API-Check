
"""
Phase 1: Copernicus Data Space scene search and downloader.

Searches Sentinel-1 SAR or Sentinel-2 optical products by bounding box
and pre/post date windows. Optionally downloads the selected full products.

Install:
    py -m pip install requests python-dotenv

.env for searching:
    No credentials required.

.env for full-product downloads:
    CDSE_USER=your_CDSE_account_email
    CDSE_PASS=your_CDSE_account_password

Note:
    CDSE OData full-product downloads use the documented account
    username/password token flow, not the Sentinel Hub client-credentials
    flow. Keep both credentials private.
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)
CATALOGUE = (
    "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
)
DOWNLOAD = (
    "https://download.dataspace.copernicus.eu/"
    "odata/v1/Products({product_id})/$value"
)

TIMEOUT = 60
CHUNK_SIZE = 1024 * 1024


def get_token() -> str:
    """Obtain a CDSE OData download token using account credentials."""
    username = os.getenv("CDSE_USER")
    password = os.getenv("CDSE_PASS")

    if not username or not password:
        raise RuntimeError(
            "Full-product downloads require CDSE_USER and CDSE_PASS "
            "in your .env file. Catalogue search does not require them."
        )

    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": "cdse-public",
            "grant_type": "password",
            "username": username,
            "password": password,
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()

    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("CDSE did not return an access token.")

    return token


def build_filter(collection, bbox, start, end, max_cloud):
    """Construct the OData filter for the requested product collection."""
    west, south, east, north = bbox

    if not (-180 <= west < east <= 180):
        raise ValueError("Invalid longitude bounds.")
    if not (-90 <= south < north <= 90):
        raise ValueError("Invalid latitude bounds.")

    polygon = (
        f"POLYGON(({west} {south},{east} {south},"
        f"{east} {north},{west} {north},{west} {south}))"
    )

    collection_name = (
        "SENTINEL-1" if collection == "S1" else "SENTINEL-2"
    )

    filters = [
        f"Collection/Name eq '{collection_name}'",
        "OData.CSC.Intersects("
        f"area=geography'SRID=4326;{polygon}')",
        f"ContentDate/Start ge {start}T00:00:00.000Z",
        f"ContentDate/Start le {end}T23:59:59.999Z",
    ]

    if collection == "S1":
        filters.append(
            "Attributes/OData.CSC.StringAttribute/any("
            "att:att/Name eq 'productType' and "
            "att/OData.CSC.StringAttribute/Value eq 'IW_GRDH_1S')"
        )
    else:
        filters.extend([
            "Attributes/OData.CSC.StringAttribute/any("
            "att:att/Name eq 'productType' and "
            "att/OData.CSC.StringAttribute/Value eq 'S2MSI2A')",
            "Attributes/OData.CSC.DoubleAttribute/any("
            "att:att/Name eq 'cloudCover' and "
            f"att/OData.CSC.DoubleAttribute/Value le {max_cloud})",
        ])

    return " and ".join(filters)


def search(collection, bbox, start, end, max_cloud, top=10):
    """Search the public product catalogue without downloading products."""
    params = {
        "$filter": build_filter(
            collection, bbox, start, end, max_cloud
        ),
        "$orderby": "ContentDate/Start desc",
        "$top": top,
    }

    response = requests.get(
        CATALOGUE, params=params, timeout=TIMEOUT
    )
    response.raise_for_status()

    products = response.json().get("value", [])

    # Follow OData pagination if the requested result limit requires it.
    while len(products) < top:
        next_link = response.json().get("@odata.nextLink")
        if not next_link:
            break

        response = requests.get(next_link, timeout=TIMEOUT)
        response.raise_for_status()
        page = response.json()
        page_products = page.get("value", [])

        if not page_products:
            break

        products.extend(page_products)

    return products[:top]


def show(label, products):
    """Display scene names, acquisition dates, and approximate sizes."""
    print(f"\n=== {label}: {len(products)} scene(s) ===")

    for index, product in enumerate(products):
        size_mb = product.get("ContentLength", 0) / 1_000_000
        date = product.get("ContentDate", {}).get("Start", "Unknown")
        print(
            f"[{index}] {product.get('Name', 'Unknown')} | "
            f"{date[:10]} | {size_mb:,.0f} MB"
        )


def safe_filename(name):
    """Prevent product names from creating arbitrary filesystem paths."""
    name = name.replace(".SAFE", "")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name + ".zip"


def download(product, token, out_dir: Path):
    """Download one full product, streaming it to disk."""
    out_dir.mkdir(parents=True, exist_ok=True)

    name = safe_filename(product["Name"])
    destination = out_dir / name

    if destination.exists():
        print(f"Already downloaded: {destination}")
        return destination

    url = DOWNLOAD.format(product_id=product["Id"])
    headers = {"Authorization": f"Bearer {token}"}

    temporary = destination.with_suffix(destination.suffix + ".part")

    try:
        with requests.Session() as session:
            response = session.get(
                url,
                headers=headers,
                allow_redirects=False,
                stream=True,
                timeout=TIMEOUT,
            )

            # Follow redirects without forwarding the bearer token to
            # a different host.
            for _ in range(10):
                if response.status_code not in (301, 302, 303, 307, 308):
                    break

                location = response.headers.get("Location")
                response.close()

                if not location:
                    raise RuntimeError(
                        "Download redirect did not provide a Location."
                    )

                next_url = urljoin(url, location)
                same_host = (
                    requests.utils.urlparse(next_url).hostname
                    == requests.utils.urlparse(url).hostname
                )

                url = next_url
                response = session.get(
                    url,
                    headers=headers if same_host else {},
                    allow_redirects=False,
                    stream=True,
                    timeout=TIMEOUT,
                )
            else:
                raise RuntimeError("Too many download redirects.")

            response.raise_for_status()

            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            last_update = time.monotonic()

            with response:
                with temporary.open("wb") as file:
                    for chunk in response.iter_content(
                        chunk_size=CHUNK_SIZE
                    ):
                        if not chunk:
                            continue

                        file.write(chunk)
                        downloaded += len(chunk)

                        if time.monotonic() - last_update >= 1:
                            if total:
                                print(
                                    f"\r  {downloaded / 1e6:,.1f} / "
                                    f"{total / 1e6:,.1f} MB",
                                    end="",
                                    flush=True,
                                )
                            else:
                                print(
                                    f"\r  {downloaded / 1e6:,.1f} MB",
                                    end="",
                                    flush=True,
                                )
                            last_update = time.monotonic()

        if temporary.stat().st_size == 0:
            raise RuntimeError("The downloaded file is empty.")

        temporary.replace(destination)
        print(f"\nSaved: {destination}")
        return destination

    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="CDSE Sentinel pre/post scene finder and downloader"
    )

    parser.add_argument(
        "--collection", choices=["S1", "S2"], default="S1"
    )
    parser.add_argument(
        "--bbox", nargs=4, type=float, required=True,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
    )
    parser.add_argument(
        "--pre", nargs=2, required=True, metavar=("START", "END")
    )
    parser.add_argument(
        "--post", nargs=2, required=True, metavar=("START", "END")
    )
    parser.add_argument(
        "--max-cloud", type=float, default=30,
        help="Maximum Sentinel-2 cloud cover percentage",
    )
    parser.add_argument(
        "--top", type=int, default=10,
        help="Maximum number of results per date window",
    )
    parser.add_argument(
        "--pre-index", type=int, default=0,
        help="PRE scene index to download",
    )
    parser.add_argument(
        "--post-index", type=int, default=0,
        help="POST scene index to download",
    )
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--out", default="data")

    args = parser.parse_args()

    if args.top < 1:
        parser.error("--top must be at least 1")
    if not 0 <= args.max_cloud <= 100:
        parser.error("--max-cloud must be between 0 and 100")

    for start, end in (args.pre, args.post):
        if start > end:
            parser.error("Each date window START must be <= END")

    try:
        print("Searching Copernicus Data Space catalogue...")

        pre = search(
            args.collection, args.bbox, *args.pre,
            args.max_cloud, args.top,
        )
        post = search(
            args.collection, args.bbox, *args.post,
            args.max_cloud, args.top,
        )

        show("PRE-event", pre)
        show("POST-event", post)

        if not pre or not post:
            sys.exit(
                "\nNo results in one or both date windows. "
                "Try wider date windows or verify the bounding box."
            )

        print(
            "\nNote: results are ordered by acquisition start time, "
            "newest first. Check orbit and acquisition metadata before "
            "using a pair for change detection."
        )

        if not args.download:
            print("\nSearch complete. No products downloaded.")
            print("Add --download to download the selected products.")
            return

        for index, products, label in (
            (args.pre_index, pre, "PRE"),
            (args.post_index, post, "POST"),
        ):
            if not 0 <= index < len(products):
                sys.exit(
                    f"{label} index {index} is out of range; "
                    f"available indices: 0 to {len(products) - 1}"
                )

        token = get_token()
        output = Path(args.out)

        print(f"\nDownloading PRE scene [{args.pre_index}]")
        download(pre[args.pre_index], token, output / "pre")

        print(f"\nDownloading POST scene [{args.post_index}]")
        download(post[args.post_index], token, output / "post")

        print("\nDownload workflow complete.")

    except requests.HTTPError as exc:
        status = (
            exc.response.status_code if exc.response is not None else "?"
        )
        detail = (
            exc.response.text[:500]
            if exc.response is not None else str(exc)
        )
        sys.exit(f"CDSE HTTP error {status}: {detail}")
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        sys.exit(f"Error: {exc}")


if __name__ == "__main__":
    main()
