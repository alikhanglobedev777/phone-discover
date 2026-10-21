"""Create a read-only model-level review queue from a detailed date-conflict CSV.

Run: python backend/scripts/triage_phone_release_dates.py DETAILS.csv --output REVIEW.csv
This does not resolve dates, normalize models, or modify phone catalog data.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

REQUIRED = {
    "brand", "device", "candidate_release_date", "ram_gb", "storage_gb",
    "upstream_path", "source_urls",
}
COLUMNS = [
    "brand", "device", "candidate_dates", "date_count", "candidate_rows",
    "distinct_upstream_files", "first_of_month_dates", "january_first_dates",
    "date_evidence_counts", "source_hosts", "review_status",
]


def build_review_rows(conflict_path):
    grouped = defaultdict(list)
    with Path(conflict_path).open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError("Missing detailed conflict columns: " +
                             ", ".join(sorted(REQUIRED - set(reader.fieldnames or []))))
        for line, row in enumerate(reader, 2):
            brand, name = row["brand"].strip(), row["device"].strip()
            if not brand or not name:
                raise ValueError(f"Missing brand/device on line {line}")
            try:
                urls = json.loads(row["source_urls"])
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid source_urls on line {line}") from error
            if not isinstance(urls, list) or not all(isinstance(url, str) for url in urls):
                raise ValueError(f"Invalid source_urls on line {line}")
            grouped[(brand.casefold(), name.casefold())].append((row, urls))

    output = []
    for key, rows in grouped.items():
        dates = sorted({row["candidate_release_date"] for row, _ in rows})
        # The input is a source-level conflict report, not a general catalog.
        # Single-date groups could indicate malformed input and must not be
        # silently presented as unresolved disagreements.
        if len(dates) <= 1:
            raise ValueError(f"Expected multiple candidate dates for {key}")
        brand, name = min(((row["brand"], row["device"]) for row, _ in rows),
                          key=lambda x: (x[0].casefold(), x[1].casefold(), x))
        date_counts = Counter(row["candidate_release_date"] for row, _ in rows)
        hosts = sorted({urlsplit(url).hostname.lower() for _, urls in rows
                        for url in urls if urlsplit(url).hostname})
        output.append({
            "brand": brand, "device": name,
            "candidate_dates": "; ".join(dates),
            "date_count": len(dates),
            "candidate_rows": len(rows),
            "distinct_upstream_files": len({row["upstream_path"] for row, _ in rows}),
            "first_of_month_dates": "; ".join(d for d in dates if d.endswith("-01")),
            "january_first_dates": "; ".join(d for d in dates if d.endswith("-01-01")),
            "date_evidence_counts": "; ".join(f"{d}: {date_counts[d]}" for d in dates),
            "source_hosts": "; ".join(hosts),
            "review_status": "unresolved",
        })
    return sorted(output, key=lambda row: (-row["candidate_rows"],
                                           -row["date_count"],
                                           row["brand"].casefold(),
                                           row["device"].casefold()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("detailed_conflicts", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = build_review_rows(args.detailed_conflicts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Unresolved model identities: {len(rows)}")
    print(f"First-of-month candidate dates: "
          f"{sum(bool(row['first_of_month_dates']) for row in rows)} model identities")
    print("Review queue:", args.output)


if __name__ == "__main__":
    main()
