"""Create a conservative, source-backed catalog CSV. No database access.

Regional/ambiguous identities are excluded, memory-only suffixes become
variants, and disputed/January-first dates become unknown rather than guessed.
"""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from unicodedata import normalize

FIELDS = ["brand", "device", "release_date", "ram_gb", "storage_gb",
          "battery_mah", "display_refresh_hz", "chipset", "operating_system",
          "colors", "source_urls", "upstream_path"]
REGIONAL = re.compile(r"\b(?:td[ -]lte|dual[ -]sim|verizon|at&t|t-mobile|docomo|softbank|vodafone|unlocked|carrier|global|international|premium edition|standard edition|japan|japanese|gsmarena copy)\b", re.I)
NON_PHONE = re.compile(r"\b(?:ipad|tablet|smartwatch|watch|galaxy tab)\b", re.I)
STORAGE = re.compile(r"\s+(\d{2,4})\s*(GB|TB)$", re.I)
PAREN_STORAGE = re.compile(r"\s*\((\d{2,4})\s*(GB|TB)\)$", re.I)
PAREN_MEMORY = re.compile(r"\s*\((\d{1,2})\s*GB(?:\s*RAM)?\s*[+/]\s*(\d{2,4})\s*(GB|TB)\)$", re.I)
PAREN_RAM = re.compile(r"\s*\((\d{1,2})\s*GB\s*RAM\)$", re.I)


def stable_slug(brand, name):
    """Retain real Plus models; Django slugify drops '+' from names."""
    raw = normalize("NFKD", f"{brand}-{name.replace('+', ' plus ')}")
    raw = raw.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[-\s]+", "-", re.sub(r"[^\w\s-]", "", raw)).strip("-_")


def clean_name(name, ram, storage):
    name = " ".join(name.strip().split())
    if not name or len(name) > 70 or REGIONAL.search(name) or NON_PHONE.search(name):
        return None
    for pattern in (PAREN_MEMORY, PAREN_RAM, PAREN_STORAGE, STORAGE):
        match = pattern.search(name)
        if not match:
            continue
        parts = match.groups()
        if pattern is PAREN_MEMORY:
            want_ram, want_storage, unit = int(parts[0]), int(parts[1]), parts[2]
            if want_ram != ram or want_storage * (1024 if unit.upper() == "TB" else 1) != storage:
                return None
        elif pattern is PAREN_RAM:
            if int(parts[0]) != ram:
                return None
        else:
            want_storage, unit = int(parts[0]), parts[1]
            if want_storage * (1024 if unit.upper() == "TB" else 1) != storage:
                return None
        name = name[:match.start()].strip()
        break
    return name if 2 <= len(name) <= 65 else None


def prepare(candidate_path, conflicts_path, output_path):
    accepted = defaultdict(list)
    reasons = Counter()
    for path, is_conflict in ((candidate_path, False), (conflicts_path, True)):
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                try:
                    ram, storage = int(row["ram_gb"]), int(row["storage_gb"])
                    if not (1 <= ram <= 64 and 16 <= storage <= 4096):
                        raise ValueError("Invalid memory")
                    name = clean_name(row["device"], ram, storage)
                    if not name:
                        reasons["uncertain_model_identity"] += 1
                        continue
                    links = json.loads(row["source_urls"])
                    if not isinstance(links, list) or not links or not all(
                        isinstance(u, str) and u.startswith("https://") for u in links
                    ):
                        raise ValueError("Invalid source links")
                    day = row["candidate_release_date"] if is_conflict else row["release_date"]
                    if day:
                        date.fromisoformat(day)
                    item = dict(row)
                    item["release_date"] = day
                    item["source_urls"] = links
                    item["device"] = name
                    accepted[(row["brand"].strip().casefold(), name.casefold(), ram, storage)].append(item)
                except (KeyError, TypeError, ValueError):
                    reasons["invalid_input"] += 1

    models = defaultdict(list)
    for (brand, name, ram, storage), items in accepted.items():
        models[(brand, name)].append((ram, storage, items))
    output_rows = []
    for key, variants in sorted(models.items()):
        if key[0] == "apple" and key[1].startswith("iphone "):
            per_storage = defaultdict(set)
            for ram, storage, _ in variants:
                per_storage[storage].add(ram)
            if any(len(rams) > 1 for rams in per_storage.values()):
                reasons["apple_conflicting_ram_model"] += 1
                continue
        dates = {row["release_date"] for _, _, items in variants for row in items if row["release_date"]}
        resolved = next(iter(dates)) if len(dates) == 1 else ""
        if resolved.endswith("-01-01"):
            resolved = ""
        if not resolved:
            reasons["models_with_unknown_date"] += 1
        for ram, storage, items in variants:
            best = max(items, key=lambda r: (
                sum(bool(r.get(f)) for f in ("chipset", "battery_mah", "display_refresh_hz",
                                              "operating_system", "colors")),
                len(r["source_urls"]), r.get("upstream_path", "")))
            fields = {}
            for field in ("chipset", "battery_mah", "display_refresh_hz", "operating_system"):
                values = {str(r.get(field, "")).strip() for r in items if r.get(field)}
                fields[field] = values.pop() if len(values) == 1 else ""
            colors = {r.get("colors", "[]") for r in items if r.get("colors") not in (None, "", "[]")}
            fields["colors"] = next(iter(colors)) if len(colors) == 1 else "[]"
            output_rows.append({
                "brand": best["brand"], "device": best["device"], "release_date": resolved,
                "ram_gb": ram, "storage_gb": storage, **fields,
                "source_urls": json.dumps(sorted({u for r in items for u in r["source_urls"]}),
                                          ensure_ascii=False),
                "upstream_path": best.get("upstream_path", ""),
            })
    # Different identities sometimes collide under slugification, including
    # punctuation/year names. Exclude both rather than merge them.
    slug_names = defaultdict(set)
    for row in output_rows:
        slug_names[stable_slug(row["brand"], row["device"])].add(
            (row["brand"].casefold(), row["device"].casefold()))
    collisions = {s for s, names in slug_names.items() if len(names) > 1}
    if collisions:
        output_rows = [r for r in output_rows
                       if stable_slug(r["brand"], r["device"]) not in collisions]
        reasons["ambiguous_slug_groups"] = len(collisions)
    brand_counts = Counter(r["brand"] for r in output_rows)
    model_count = len({(r["brand"].casefold(), r["device"].casefold()) for r in output_rows})
    if model_count < 500 or len(brand_counts) != 10:
        raise RuntimeError("Insufficient validated catalog coverage")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(sorted(output_rows, key=lambda r:
            (r["brand"], r["device"], int(r["ram_gb"]), int(r["storage_gb"]))))
    print(f"IMPORT CANDIDATE: {model_count} models, {len(output_rows)} variants")
    print("Brand coverage:", dict(sorted(brand_counts.items())))
    print("Excluded/unknown:", dict(sorted(reasons.items())))
    return output_rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_csv", type=Path)
    parser.add_argument("conflicts_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.candidate_csv, args.conflicts_csv, args.output)
