"""Merge authentic manufacturer model-page images; reject any source ambiguity."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

from discover_official_manufacturer_photos import (
    COLUMNS, SOURCES, VALIDATION, image_url_approved, official_pages,
)


def merge(shards, missing_csv, target, parts=2):
    shards = Path(shards)
    files = [shards / f"{brand.lower()}-{part}.csv"
             for brand in SOURCES for part in range(parts)]
    if any(not file.is_file() for file in files):
        raise RuntimeError("All official manufacturer evidence shards are required")
    with Path(missing_csv).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = {(row["brand"].strip().casefold(), row["device"].strip().casefold())
                   for row in reader}
    seen = {}
    ambiguous = set()
    for path in files:
        with path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if not set(COLUMNS).issubset(reader.fieldnames or []):
                raise RuntimeError(f"Missing evidence columns in {path}")
            for line, row in enumerate(reader, 2):
                brand, model = row["brand"].strip(), row["device"].strip()
                key = (brand.casefold(), model.casefold())
                if (brand not in SOURCES or key not in missing or
                    row["publisher"] != brand or
                    row["source_validation"] != VALIDATION or
                    row["source_url"] not in official_pages(brand, model) or
                    not image_url_approved(brand, row["image_url"])):
                    raise RuntimeError(f"Untrusted manufacturer/source evidence {path}:{line}")
                if key in seen and seen[key] != row:
                    ambiguous.add(key)
                else:
                    seen.setdefault(key, row)
    owners = defaultdict(set)
    for key, row in seen.items():
        owners[row["image_url"]].add(key)
    shared = {url for url, users in owners.items() if len(users) > 1}
    clean = [
        {col: row[col] for col in COLUMNS}
        for key, row in seen.items()
        if key not in ambiguous and row["image_url"] not in shared
    ]
    output = Path(target)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(sorted(clean, key=lambda r: (
            r["brand"].casefold(), r["device"].casefold())))
    print(f"Official model images: {len(clean)} unambiguous matched products, "
          f"{len(ambiguous)} contradictory identities and "
          f"{len(shared)} cross-model images excluded.", flush=True)
    return clean


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shards", type=Path)
    parser.add_argument("missing_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parts", type=int, default=2)
    opts = parser.parse_args()
    merge(opts.shards, opts.missing_csv, opts.output, opts.parts)
