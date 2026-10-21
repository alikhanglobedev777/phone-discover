"""Merge exact-model WhatMobile technical-detail shards, quarantine ambiguity.

No fields are invented; only explicitly captured data and gallery links are
written. Each source URL is retained for attribution and later review.
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from collect_whatmobile_details import FIELDS, SECTIONS

HOSTS = {"whatmobile.com.pk", "www.whatmobile.com.pk"}


def safe_url(url, image=False):
    try:
        parts = urlsplit(url)
        return (parts.scheme == "https" and parts.hostname in HOSTS and
                (not image or "/admin/images/" in parts.path.casefold()))
    except ValueError:
        return False


def merge(shard_dir, output_path, min_models=100):
    shard_dir = Path(shard_dir)
    files = [shard_dir / f"whatmobile_details_{i}.csv" for i in (0, 1, 2)]
    if any(not p.exists() for p in files):
        raise ValueError("All 3 WhatMobile detail shards are required")
    matched = defaultdict(list)
    for path in files:
        with path.open(newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            if not set(FIELDS).issubset(reader.fieldnames or []):
                raise ValueError(f"Missing required evidence fields: {path}")
            for number, row in enumerate(reader, 2):
                try:
                    brand, name = row["brand"].strip(), row["device"].strip()
                    if not brand or not name or not safe_url(row["product_page"]):
                        raise ValueError("model identity or source URL")
                    sections = json.loads(row["spec_sections_json"])
                    photos = json.loads(row["gallery_json"])
                    if not isinstance(sections, dict) or not isinstance(photos, list):
                        raise ValueError("invalid structured evidence")
                    if any(section not in SECTIONS.values() or not isinstance(items, dict) or
                           len(items) > 36 or any(
                               not isinstance(k, str) or not isinstance(v, str) or
                               not 1 <= len(k) <= 90 or not 1 <= len(v) <= 900
                               for k, v in items.items())
                           for section, items in sections.items()):
                        raise ValueError("unrecognized spec section")
                    if len(photos) > 8 or any(not isinstance(u, str) or len(u) > 1000 or
                                              not safe_url(u, image=True) for u in photos):
                        raise ValueError("untrusted gallery image URL")
                    os_name, chipset = row["operating_system"].strip(), row["chipset"].strip()
                    if len(os_name) > 80 or len(chipset) > 160:
                        raise ValueError("oversized OS/chipset")
                    battery = int(row["battery_mah"]) if row["battery_mah"].strip() else None
                    refresh = int(row["refresh_hz"]) if row["refresh_hz"].strip() else None
                    if battery is not None and not 500 <= battery <= 30000:
                        raise ValueError("implausible battery")
                    if refresh is not None and not 60 <= refresh <= 240:
                        raise ValueError("implausible display refresh")
                except (KeyError, ValueError, TypeError) as error:
                    raise ValueError(f"Unsafe source record {path}:{number}: {error}") from error
                matched[(brand.casefold(), name.casefold())].append(row)

    clean = []
    quarantined = 0
    for key, rows in sorted(matched.items()):
        # Duplicate case spellings can be collapsed only if every documented
        # fact is identical, including gallery links, specification sections.
        facts = {
            (r["product_page"], r["operating_system"], r["chipset"],
             r["battery_mah"], r["refresh_hz"], r["spec_sections_json"],
             r["gallery_json"])
            for r in rows
        }
        if len(facts) > 1:
            quarantined += 1
            continue
        clean.append(min(rows, key=lambda r: (r["brand"], r["device"])))
    # An image URL claimed by multiple models isn't source-verified enough
    # to attribute a gallery angle. Remove those URLS, keep the spec details.
    owners = defaultdict(set)
    for row in clean:
        for url in json.loads(row["gallery_json"]):
            owners[url].add((row["brand"].casefold(), row["device"].casefold()))
    unsafe = {url for url, users in owners.items() if len(users) > 1}
    for row in clean:
        if unsafe:
            row["gallery_json"] = json.dumps(
                [u for u in json.loads(row["gallery_json"]) if u not in unsafe])
    if len(clean) < min_models:
        raise RuntimeError(f"Only {len(clean)} reliable specification records found")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(clean)
    print(f"Verified {len(clean)} phones with technical specs, "
          f"{quarantined} ambiguous identities excluded, "
          f"{len(unsafe)} shared photo URLs excluded.", flush=True)
    return clean


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shards", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-models", type=int, default=100)
    options = parser.parse_args()
    merge(options.shards, options.output, options.min_models)
