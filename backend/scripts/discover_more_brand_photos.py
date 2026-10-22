"""Second-pass, read-only discovery for production phones still missing images.

Search alternate official GSMArena CDN filenames, while preserving full
brand+model identity (including Pro, Max, Ultra, Fold, 4G and 5G). Each URL
must return actual JPEG bytes; guesses never enter the saved manifest.

The input is the image-gap snapshot exported read-only from Render, not an
entire model dump. NO scraping behind challenge pages or authentication.
"""
import argparse
import csv
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from discover_missing_brand_images import (
    BRANDS, COLUMNS, HOST, VALIDATION, model_image_urls, model_slug, root_names,
    valid_jpeg,
)

SUFFIXES = ("-3", "-4", "-5", "-6", "-01", "-02", "-03", "-a", "-b")
CDN_HOSTS = ("fdn2.gsmarena.com", "fdn.gsmarena.com")


def additional_roots(brand, model):
    """Alternative *full* model spellings only; never trim edition suffixes."""
    base = list(root_names(brand, model))
    slug = model_slug(model)
    # Major Motorola range appears with and without 'moto' in CDN naming.
    # 'G84 5G' and 'Moto G84 5G' are the same full model tokens.
    if brand == "Motorola" and re.match(r"^(?:g\d|e\d|edge-)", slug):
        base.append("motorola-moto-" + slug)
    if brand == "Motorola" and slug.startswith("moto-"):
        base.append("motorola-" + slug[5:])
    # GSMArena's Xiaomi subbrand images may be catalogued as POCO or Redmi,
    # but only when the *full name already contains that subbrand*.
    if brand == "Xiaomi" and slug.startswith(("poco-", "redmi-")):
        base.append(slug)
    # Preserve variant qualifiers; 'Note 40 Pro 5G' isn't 'Note 40 Pro'.
    if brand == "Samsung" and slug.startswith("galaxy-z-flip-"):
        base.append("samsung-" + slug.replace("flip-", "flip", 1))
    if brand == "Samsung" and slug.startswith("galaxy-z-fold-"):
        base.append("samsung-" + slug.replace("fold-", "fold", 1))
    return list(dict.fromkeys(base))


def second_pass_candidates(brand, model):
    """Only alternate full-model GSMArena file naming conventions."""
    roots = additional_roots(brand, model)
    folder = BRANDS[brand][1]
    seen = set()
    for root in roots:
        for suffix in SUFFIXES:
            # First try historically known reliable fdn2 host.
            path = f"/vv/pics/{folder}/{root}{suffix}.jpg"
            for hostname in CDN_HOSTS:
                url = f"https://{hostname}{path}"
                if url not in seen:
                    seen.add(url)
                    yield url
        # A number of models use a secondary bigpic suffix instead.
        for suffix in ("-1", "-2"):
            for hostname in CDN_HOSTS:
                url = f"https://{hostname}/vv/bigpic/{root}{suffix}.jpg"
                if url not in seen:
                    seen.add(url)
                    yield url


def is_exact_image_path(url, brand, device):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in CDN_HOSTS
            or parsed.query or parsed.fragment):
        return False
    return url in set(second_pass_candidates(brand, device))


def scan(gap_csv, output_csv, brand, part=0, parts=2, checker=valid_jpeg, pace=0.06):
    if brand not in BRANDS or not (1 <= parts <= 10 and 0 <= part < parts):
        raise ValueError("Invalid brand/partition")
    with Path(gap_csv).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not {"brand", "device"}.issubset(reader.fieldnames or []):
            raise ValueError("Expected brand,device gap manifest")
        names = sorted({
            row["device"].strip() for row in reader
            if row["brand"].strip().casefold() == brand.casefold()
               and row["device"].strip()
        }, key=str.casefold)
    selected = names[part::parts]
    result = []
    for i, name in enumerate(selected, start=1):
        for url in second_pass_candidates(brand, name):
            if checker(url):
                result.append({
                    "brand": brand, "device": name,
                    "image_url": url, "publisher": "GSMArena",
                    "source_url": url, "source_validation": VALIDATION,
                })
                break
            if pace:
                time.sleep(pace)
        if i % 25 == 0:
            print(f"{brand} retry shard {part}: {i}/{len(selected)} scanned, "
                  f"{len(result)} additional JPEGs", flush=True)
    output = Path(output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(result)
    print(f"Additional {brand} photos: {len(result)} verified of {len(selected)} missing models.", flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gap_csv", type=Path)
    parser.add_argument("--brand", choices=BRANDS, required=True)
    parser.add_argument("--part", type=int, default=0)
    parser.add_argument("--parts", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scan(args.gap_csv, args.output, args.brand, args.part, args.parts)
