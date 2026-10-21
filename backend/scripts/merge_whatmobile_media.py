"""Validate and combine sharded WhatMobile image reports before production import.

Usage:
 python backend/scripts/merge_whatmobile_media.py shards/ \
     --output backend/data/whatmobile_media.csv --min-photos 5
Fails closed: duplicates, unauthorised publishers, invalid URLs, or too few
working image references do not create a migration or change production data.
"""
import argparse
import csv
from pathlib import Path
from urllib.parse import urlsplit

FIELDS = ("brand", "device", "source", "product_page",
          "image_url", "colors", "review_status")
SITE = {"www.whatmobile.com.pk", "whatmobile.com.pk"}
RIGHTS = "USER_CONFIRMED_WHATMOBILE"


def validate_url(url, photo=False):
    if not isinstance(url, str) or len(url) > 1000:
        return False
    data = urlsplit(url)
    if data.scheme != "https" or data.hostname not in SITE:
        return False
    return not photo or "/admin/images/" in data.path.casefold()


def merge(shard_dir, output, min_photos=5, expected_shards=3):
    input_files = sorted(Path(shard_dir).glob("whatmobile_media_*.csv"))
    if len(input_files) != expected_shards:
        raise ValueError(f"Expected {expected_shards} shard files; found {len(input_files)}")
    found = []
    seen = set()
    for file in input_files:
        with file.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not set(FIELDS).issubset(reader.fieldnames or []):
                raise ValueError(f"Missing columns in {file}")
            for number, row in enumerate(reader, start=2):
                brand, name = row["brand"].strip(), row["device"].strip()
                key = (brand.casefold(), name.casefold())
                if (not brand or not name or key in seen or
                    row["source"] != "WhatMobile" or
                    row["review_status"] != RIGHTS or
                    not validate_url(row["product_page"]) or
                    not validate_url(row["image_url"], photo=True)):
                    raise ValueError(f"Invalid/duplicate model-source evidence {file}:{number}")
                colors = [v.strip() for v in row["colors"].split(",") if v.strip()]
                if len(colors) > 12 or any(len(v) > 80 for v in colors):
                    raise ValueError(f"Invalid color data {file}:{number}")
                seen.add(key)
                found.append({field: row[field] for field in FIELDS})

    if len(found) < min_photos:
        raise RuntimeError(
            f"Only {len(found)} accessible exact-model images found. "
            "Cannot publish bulk media import; inspect crawler/robots/HTTP errors."
        )
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(sorted(found, key=lambda x: (x["brand"].casefold(),
                                                      x["device"].casefold())))
    print(f"Verified manifest for {len(found)} unique WhatMobile phone models: {out}", flush=True)
    return found


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shard_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-photos", type=int, default=5)
    args = parser.parse_args()
    merge(args.shard_dir, args.output, args.min_photos)
