"""Build source-attributed 2020+ phone CSV from the pinned TechAPI checkout.

Run from the repository root: python backend/scripts/build_phone_csv.py UPSTREAM_DIR
The TechAPI data is CC BY-SA 4.0; preserve upstream attribution on reuse.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

BRANDS = {"apple": "Apple", "samsung": "Samsung", "google": "Google",
          "oppo": "Oppo", "vivo": "Vivo", "xiaomi": "Xiaomi",
          "motorola": "Motorola", "infinix": "Infinix",
          "tecno": "Tecno", "itel": "Itel"}
FIELDS = ["brand", "device", "release_date", "ram_gb", "storage_gb",
          "battery_mah", "display_refresh_hz", "chipset",
          "operating_system", "colors", "source_urls", "upstream_path"]
OUTPUT = Path("backend/data/phones_2020_onward.csv")

def positive(value, low, high):
    try:
        n = int(value)
        return n if low <= n <= high else None
    except (ValueError, TypeError):
        return None

def variants(record):
    ram = positive(record.get("ram_gb"), 1, 64)
    storages = record.get("storage_options_gb") or ([record.get("storage_gb")] if record.get("storage_gb") else [])
    if not isinstance(storages, list):
        return []
    valid_storages = set()
    for raw in storages:
        storage = positive(raw, 4, 4096)
        if storage is not None:
            valid_storages.add(storage)
    return [(ram, storage) for storage in sorted(valid_storages)] if ram else []

def create_csv(source_root, output=OUTPUT):
    source_root = Path(source_root)
    if (source_root / "data" / "smartphone").is_dir():
        base = source_root / "data" / "smartphone"
    else:
        base = source_root / "smartphone"
    today = date.today()
    records = {}
    skipped = defaultdict(int)
    for brand_slug, brand in BRANDS.items():
        for year in range(2020, today.year + 1):
            for path in sorted((base / brand_slug / str(year)).glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    released = date.fromisoformat(str(data.get("release_date", "")))
                    name = str(data.get("name") or "").strip()
                    sources = data.get("source_urls") or []
                    if not 2020 <= released.year <= today.year or released > today:
                        skipped["bad_release_date"] += 1
                        continue
                    if not name or len(name) > 180 or not isinstance(sources, list) or not sources or not all(
                        isinstance(x, str) and x.startswith("https://") for x in sources
                    ):
                        skipped["identity_or_sources"] += 1
                        continue
                    # Keep the original manufacturer name, without inventing a Pakistan SKU.
                    if name.casefold().startswith(brand.casefold() + " "):
                        name = name[len(brand):].strip()
                    options = variants(data)
                    if not options:
                        skipped["no_ram_storage"] += 1
                        continue
                    finishes = data.get("colors") or []
                    if isinstance(finishes, str):
                        finishes = [s.strip() for s in finishes.split(",")]
                    if not isinstance(finishes, list):
                        finishes = []
                    finishes = sorted(set(c.strip() for c in finishes if isinstance(c, str) and 1 < len(c.strip()) <= 80))
                    display = data.get("display") if isinstance(data.get("display"), dict) else {}
                    for ram, storage in options:
                        key = (brand.casefold(), name.casefold(), ram, storage)
                        row = {
                            "brand": brand, "device": name, "release_date": released.isoformat(),
                            "ram_gb": ram, "storage_gb": storage,
                            "battery_mah": positive(data.get("battery_mah"), 500, 30000) or "",
                            "display_refresh_hz": positive(display.get("refresh_hz"), 24, 240) or "",
                            "chipset": str(data.get("soc") or "")[:160],
                            "operating_system": str(data.get("os") or "")[:80],
                            "colors": json.dumps(finishes, ensure_ascii=False),
                            "source_urls": json.dumps(sources, ensure_ascii=False),
                            "upstream_path": str(path.relative_to(source_root)).replace("\\", "/"),
                        }
                        # Prefer an entry with more source detail; deterministic duplicate resolution.
                        if key not in records or len(row["source_urls"]) + len(row["colors"]) > len(records[key]["source_urls"]) + len(records[key]["colors"]):
                            records[key] = row
                except (ValueError, OSError, TypeError, json.JSONDecodeError):
                    skipped["unreadable"] += 1
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records[k] for k in sorted(records))
    print(f"Wrote {len(records)} source-attributed variant rows to {output}")
    print("Skipped:", dict(skipped))
    if len(records) < 500:
        raise RuntimeError("Too few records for full-catalog candidate. Do not import.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python backend/scripts/build_phone_csv.py PATH_TO_TECHAPI_CHECKOUT")
    create_csv(sys.argv[1])
