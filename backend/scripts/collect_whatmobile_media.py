"""Discover actual WhatMobile photos and documented colors for exact catalog models.

The Phone Discover operator confirms image reuse permission from WhatMobile.
No PriceOye content is used. Respect robots.txt, validate the source page and
image response, don't bypass 403/challenges, and never match partial model names.

This outputs a source-backed CSV; the GitHub workflow validates and imports
it via a single additive Django migration on the next Render deploy.
"""
import argparse
import csv
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from discover_retailer_phone_images import (
    Page, LimitedFetcher, image_from_page, same_model, COLUMNS, USER_AGENT,
)

ALLOWED_HOSTS = {"www.whatmobile.com.pk", "whatmobile.com.pk"}
IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}
PHOTO_TIMEOUT = 12


def photo_is_accessible(url, fetcher):
    """Test the actual image URL; a 404 or HTML page is not a product photo."""
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or "/admin/images/" not in parsed.path.lower()
            or not fetcher.can_fetch(url)):
        return False
    try:
        req = Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/avif,image/webp,image/png,image/jpeg",
            "Range": "bytes=0-1023",
        })
        with urlopen(req, timeout=PHOTO_TIMEOUT) as response:
            if urlparse(response.geturl()).hostname not in ALLOWED_HOSTS:
                return False
            mime = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if mime not in IMAGE_MIME:
                return False
            signature = response.read(32)
            return (signature.startswith(b"\xff\xd8\xff") or
                    signature.startswith(b"\x89PNG\r\n\x1a\n") or
                    signature.startswith(b"RIFF") and signature[8:12] == b"WEBP")
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return False


def candidate_paths(brand, model):
    raw = model.strip().replace(" ", "-")
    paths = [raw]
    cleaned = raw.replace("(", "").replace(")", "")
    if cleaned != raw:
        paths.append(cleaned)
    # Retain exact identity from the H1 regardless of URL variation.
    return [
        f"https://www.whatmobile.com.pk/{quote(brand.title())}_{quote(path)}"
        for path in dict.fromkeys(paths)
    ]


def discover(input_path, output_path, start=0, limit=750):
    if start < 0 or not 1 <= limit <= 1000:
        raise ValueError("start must be >=0, limit between 1 and 1000")
    with Path(input_path).open(encoding="utf-8-sig", newline="") as source:
        rows = csv.DictReader(source)
        models = sorted({(row["brand"].strip(), row["device"].strip())
                         for row in rows if row["brand"].strip() and row["device"].strip()})
    selected = models[start:start+limit]
    fetcher = LimitedFetcher()
    results = []
    missing = 0
    for index, (brand, device) in enumerate(selected, start + 1):
        found = False
        for page_url in candidate_paths(brand, device):
            content = fetcher.fetch(page_url)
            if not content:
                continue
            parser = Page()
            parser.feed(content)
            # Only the exact model header; do not accept a similar variant.
            title = " ".join(parser.h1).strip()
            if not same_model(title, brand, device):
                continue
            image_url = image_from_page(parser, page_url, brand, device, "WhatMobile")
            if not image_url or not photo_is_accessible(image_url, fetcher):
                continue
            results.append({
                "brand": brand, "device": device,
                "source": "WhatMobile", "product_page": page_url,
                "image_url": image_url, "colors": parser.first_color_names(),
                "review_status": "USER_CONFIRMED_WHATMOBILE",
            })
            found = True
            break
        if not found:
            missing += 1
        if (index-start) % 50 == 0:
            print(f"Progress {index-start}/{len(selected)}: "
                  f"{len(results)} exact, accessible images; {missing} unmatched", flush=True)
        # Avoid bursts of requests against publisher site.
        time.sleep(0.25)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(results)
    print(f"Finished shard: {len(results)} real WhatMobile images, "
          f"{missing} missing/unverified out of {len(selected)} models", flush=True)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog_csv", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=750)
    args = parser.parse_args()
    discover(args.catalog_csv, args.output, args.start, args.limit)
