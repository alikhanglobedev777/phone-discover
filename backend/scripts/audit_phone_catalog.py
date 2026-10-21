"""Read-only quality report for a candidate phone catalog CSV.

Run: python backend/scripts/audit_phone_catalog.py INPUT.csv --output REPORT.csv
Add --strict to fail if any review flags remain. Does not change imported data.
"""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

MEMORY = re.compile(r"\s+\d{2,4}\s*GB$", re.I)
NON_PHONE = re.compile(r"\b(?:ipad|tablet|smartwatch|watch|galaxy tab)\b", re.I)
REGION = re.compile(r"\b(?:verizon|at&t|t-mobile|vodafone|docomo|softbank|china version|global version|international version|unlocked|carrier)\b", re.I)


def audit(path):
    findings = []
    groups = defaultdict(list)
    exact = defaultdict(list)
    brands = Counter()
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"brand", "device", "release_date", "ram_gb", "storage_gb", "source_urls"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Missing CSV columns: " + ", ".join(sorted(required - set(reader.fieldnames or []))))
        for line, row in enumerate(reader, 2):
            brand, name = row["brand"].strip(), row["device"].strip()
            brands[brand] += 1
            base = MEMORY.sub("", name).strip().casefold()
            groups[(brand.casefold(), base)].append((line, name))
            exact[(brand.casefold(), name.casefold(), row["ram_gb"], row["storage_gb"])].append(line)

            def flag(code, detail):
                findings.append((code, line, brand, name, detail, row.get("upstream_path", "")))

            try:
                released = date.fromisoformat(row["release_date"])
                if (released.month, released.day) == (1, 1):
                    flag("REVIEW_JAN_1_DATE", row["release_date"])
                if released.year < 2020 or released > date.today():
                    flag("INVALID_DATE", row["release_date"])
            except ValueError:
                flag("INVALID_DATE", row["release_date"])
            try:
                ram, storage = int(row["ram_gb"]), int(row["storage_gb"])
                if not (1 <= ram <= 64 and 16 <= storage <= 4096):
                    flag("INVALID_MEMORY", f"RAM={ram}; storage={storage}")
            except ValueError:
                flag("INVALID_MEMORY", f"RAM={row['ram_gb']}; storage={row['storage_gb']}")
            if NON_PHONE.search(name):
                flag("REVIEW_NON_PHONE_NAME", "Possible tablet/wearable")
            if REGION.search(name):
                flag("REVIEW_REGIONAL_IDENTITY", "Possible carrier/region-specific identity")
            if MEMORY.search(name):
                flag("REVIEW_MEMORY_IN_NAME", "Storage suffix in device name")
            if len(name) > 70:
                flag("REVIEW_LONG_NAME", f"Length={len(name)}")
            try:
                urls = json.loads(row["source_urls"])
                if not isinstance(urls, list) or not urls or not all(isinstance(u, str) and u.startswith("https://") for u in urls):
                    flag("INVALID_SOURCES", "Missing or malformed sources")
            except (ValueError, TypeError):
                flag("INVALID_SOURCES", "Malformed source JSON")

    for (brand, base), members in groups.items():
        names = sorted({name for _, name in members})
        if len(names) > 1:
            line, name = min(members)
            findings.append(("REVIEW_POSSIBLE_SAME_MODEL", line, brand, name,
                             "Candidate base: " + base + "; names: " + " | ".join(names[:12]), ""))
    for key, lines in exact.items():
        if len(lines) > 1:
            findings.append(("DUPLICATE_EXACT_VARIANT", lines[0], key[0], key[1],
                             "CSV lines: " + ", ".join(map(str, lines)), ""))
    return sorted(findings, key=lambda x: (x[1], x[0])), brands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    options = parser.parse_args()
    findings, brands = audit(options.csv_path)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    with options.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["finding", "csv_line", "brand", "device", "detail", "upstream_path"])
        writer.writerows(findings)
    print("Rows by brand:", dict(sorted(brands.items())))
    print("Findings:", dict(sorted(Counter(item[0] for item in findings).items())))
    print("Report:", options.output)
    if options.strict and findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
