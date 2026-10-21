"""Checks source grouping and non-mutating, reproducible date-review reports."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from triage_phone_release_dates import build_review_rows

COLUMNS = ["brand", "device", "candidate_release_date", "ram_gb",
           "storage_gb", "upstream_path", "source_urls"]


class ReleaseDateTriageTests(unittest.TestCase):
    def make_report(self, rows):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "conflicts.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_casefold_groups_sources_and_distinguishes_month_first(self):
        rows = [
            dict(brand="Oppo", device="Find X5 Pro", candidate_release_date="2022-01-01",
                 ram_gb="12", storage_gb="256", upstream_path="a.json",
                 source_urls=json.dumps(["https://dataset.example.org/first"])),
            dict(brand="OPPO", device="find x5 pro", candidate_release_date="2022-03-14",
                 ram_gb="12", storage_gb="256", upstream_path="b.json",
                 source_urls=json.dumps(["https://www.oppo.com/en/newsroom/press/"])),
        ]
        path = self.make_report(rows)
        old = path.read_bytes()
        review = build_review_rows(path)
        self.assertEqual(path.read_bytes(), old)
        self.assertEqual(len(review), 1)
        self.assertEqual(review[0]["candidate_dates"], "2022-01-01; 2022-03-14")
        self.assertEqual(review[0]["candidate_rows"], 2)
        self.assertEqual(review[0]["distinct_upstream_files"], 2)
        self.assertEqual(review[0]["first_of_month_dates"], "2022-01-01")
        self.assertEqual(review[0]["january_first_dates"], "2022-01-01")
        self.assertEqual(review[0]["review_status"], "unresolved")
        self.assertIn("oppo.com", review[0]["source_hosts"])

    def test_single_date_is_rejected(self):
        path = self.make_report([dict(brand="Apple", device="iPhone 12",
            candidate_release_date="2020-10-23", ram_gb="4", storage_gb="64",
            upstream_path="one.json", source_urls="[]")])
        with self.assertRaisesRegex(ValueError, "Expected multiple candidate dates"):
            build_review_rows(path)

    def test_requires_provenance_columns(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "old.csv"
        path.write_text("brand,device,conflicting_release_dates\nApple,iPhone 12,2020-10-23\n",
                        encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Missing detailed conflict columns"):
            build_review_rows(path)


if __name__ == "__main__":
    unittest.main()
