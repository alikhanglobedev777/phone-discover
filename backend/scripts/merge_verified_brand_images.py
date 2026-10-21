"""Merge exact-model source-tested image shards; quarantine photo collisions.

No network or database access. Workflow commits this manifest alongside a
transactional, create-only Django migration only after all shards finish.
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

from discover_missing_brand_images import (
    BRANDS, COLUMNS, VALIDATION, valid_source_url,
)


def merge(shards, catalog_path, output_path, parts=2, min_images=1):
    shards = Path(shards)
    files = [shards / f"{brand.lower()}-{part}.csv"
             for brand in BRANDS for part in range(parts)]
    if any(not file.is_file() for file in files):
        missing = [str(f) for f in files if not f.is_file()]
        raise RuntimeError(f"Missing scan shards: {missing[:4]}")
    with Path(catalog_path).open(encoding="utf-8-sig", newline="") as handle:
        catalog = {
            (r["brand"].strip().casefold(), r["device"].strip().casefold())
            for r in csv.DictReader(handle)
        }

    rows = {}
    conflicting = set()
    for file in files:
        with file.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if not set(COLUMNS).issubset(reader.fieldnames or []):
                raise ValueError(f"Incomplete source manifest: {file}")
            for line, row in enumerate(reader, 2):
                brand, name = row["brand"].strip(), row["device"].strip()
                key = (brand.casefold(), name.casefold())
                if (brand not in BRANDS or key not in catalog or
                    row["publisher"] != "GSMArena" or
                    row["source_validation"] != VALIDATION or
                    row["source_url"] != row["image_url"] or
                    not valid_source_url(row["image_url"], brand, name)):
                    raise ValueError(f"Source identity or image provenance invalid: {file}:{line}")
                record = {field: row[field] for field in COLUMNS}
                if key in rows and rows[key]["image_url"] != record["image_url"]:
                    conflicting.add(key)
                else:
                    rows.setdefault(key, record)

    # One CDN image belonging to multiple DIFFERENT models is suspicious.
    image_owners = defaultdict(set)
    for key, row in rows.items():
        image_owners[row["image_url"]].add(key)
    shared = {url for url, owners in image_owners.items() if len(owners) > 1}
    verified = [
        row for key, row in rows.items()
        if key not in conflicting and row["image_url"] not in shared
    ]
    if len(verified) < min_images:
        raise RuntimeError(
            f"Only {len(verified)} unambiguous image matches; no import will be committed."
        )
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(sorted(verified, key=lambda r: (
            r["brand"].casefold(), r["device"].casefold(),
        )))
    print(f"Verified media: {len(verified)} exact phone identities; "
          f"quarantined {len(conflicting)} contradictory identities and "
          f"{len(shared)} photos reused by multiple models.", flush=True)
    return verified


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shards", type=Path)
    parser.add_argument("catalog_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parts", type=int, default=2)
    parser.add_argument("--min-images", type=int, default=1)
    args = parser.parse_args()
    merge(args.shards, args.catalog_csv, args.output, args.parts, args.min_images)
