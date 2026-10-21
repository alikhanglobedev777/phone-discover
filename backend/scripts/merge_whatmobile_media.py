"""Merge completed WhatMobile scan shards into one conservative import manifest.

Only source-validated records with an exact case-insensitive identity are kept.
Aliases differing only by capitalization are deduplicated if they agree about
the product photo AND documented colors. No two different models may reuse
the same WhatMobile photo. Ambiguous identities/images are quarantined.
"""
import argparse
import csv
from collections import defaultdict
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
    shard_dir = Path(shard_dir)
    input_files = [shard_dir / f"whatmobile_media_{i}.csv"
                   for i in range(expected_shards)]
    if any(not f.is_file() for f in input_files):
        raise ValueError(f"Expected shards 0..{expected_shards - 1} in {shard_dir}")

    variants = defaultdict(list)
    raw_count = 0
    for file in input_files:
        with file.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not set(FIELDS).issubset(reader.fieldnames or []):
                raise ValueError(f"Missing columns in {file}")
            for line, row in enumerate(reader, start=2):
                brand, name = row["brand"].strip(), row["device"].strip()
                if (not brand or not name or
                    row["source"] != "WhatMobile" or
                    row["review_status"] != RIGHTS or
                    not validate_url(row["product_page"]) or
                    not validate_url(row["image_url"], photo=True)):
                    raise ValueError(f"Invalid publisher/photo evidence {file}:{line}")
                colors = [v.strip() for v in row["colors"].split(",") if v.strip()]
                if len(colors) > 12 or any(len(v) > 80 for v in colors):
                    raise ValueError(f"Invalid documented colors {file}:{line}")
                key = (brand.casefold(), name.casefold())
                variants[key].append((row, tuple(colors)))
                raw_count += 1

    winners = {}
    ambiguous_identity = set()
    capitalization_duplicates = 0
    for key, items in variants.items():
        photo_urls = {row["image_url"] for row, _ in items}
        normalized_colors = {tuple(c.casefold() for c in colors)
                             for _, colors in items}
        if len(photo_urls) > 1 or len(normalized_colors) > 1:
            ambiguous_identity.add(key)
            continue
        capitalization_duplicates += len(items) - 1
        # Stable selection; never arbitrarily choose between disagreeing photos.
        row = min((row for row, _ in items),
                  key=lambda record: (record["device"], record["product_page"]))
        winners[key] = {field: row[field] for field in FIELDS}

    photo_owners = defaultdict(set)
    for key, row in winners.items():
        photo_owners[row["image_url"]].add(key)
    shared_images = {url for url, keys in photo_owners.items()
                     if len(keys) > 1}
    # Two separate identities claiming the same image can mean the publisher
    # reused the wrong file (Pro versus base, Plus, etc). Exclude all owners.
    found = [row for key, row in winners.items()
             if row["image_url"] not in shared_images]

    if len(found) < min_photos:
        raise RuntimeError(
            f"Only {len(found)} unambiguous WhatMobile images found. "
            "Cannot publish an image migration."
        )
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(sorted(found, key=lambda x: (x["brand"].casefold(),
                                                      x["device"].casefold())))
    print(
        f"WhatMobile: {raw_count} source rows, {len(variants)} distinct names, "
        f"{capitalization_duplicates} identical case aliases collapsed, "
        f"{len(ambiguous_identity)} contradictory identities removed, "
        f"{len(shared_images)} images reused for different phone models removed, "
        f"{len(found)} final exact-model photo records.",
        flush=True,
    )
    return found


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shard_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-photos", type=int, default=5)
    args = parser.parse_args()
    merge(args.shard_dir, args.output, args.min_photos)
