"""Regression checks for read-only phone catalog warnings (no Django setup)."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from audit_phone_catalog import audit


FIELDS = ["brand", "device", "release_date", "ram_gb", "storage_gb",
          "source_urls", "upstream_path"]


def record(brand, name, ram, storage, path):
    return {"brand": brand, "device": name, "release_date": "2020-10-23",
            "ram_gb": str(ram), "storage_gb": str(storage),
            "source_urls": json.dumps(["https://example.org/specifications"]),
            "upstream_path": path}


class CatalogAuditTests(unittest.TestCase):
    def test_regional_name_and_apple_ram_disagreement_are_review_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "phones.csv"
            rows = [
                record("Apple", "iPhone 12", 4, 64, "apple-primary.json"),
                record("Apple", "iPhone 12", 6, 64, "apple-secondary.json"),
                record("Apple", "iPhone 12 mini", 4, 64, "apple-mini.json"),
                record("Samsung",
                       "SM-A022F Galaxy A02 Standard Edition Global Dual SIM TD-LTE 64GB",
                       3, 64, "samsung-region.json"),
            ]
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            original_bytes = path.read_bytes()
            findings, brands = audit(path)
            self.assertEqual(original_bytes, path.read_bytes())
            self.assertEqual(brands["Apple"], 3)
            regional = [x for x in findings if x[0] == "REVIEW_REGIONAL_IDENTITY"]
            self.assertEqual(len(regional), 1)
            self.assertIn("SM-A022F", regional[0][3])
            conflicts = [x for x in findings if x[0] == "REVIEW_APPLE_RAM_DISAGREEMENT"]
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0][3], "iPhone 12")
            self.assertIn("apple-primary.json", conflicts[0][4])
            self.assertIn("apple-secondary.json", conflicts[0][4])

    def test_no_automatic_merging_of_different_iphone_models(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "phones.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows([
                    record("Apple", "iPhone 12", 4, 64, "standard.json"),
                    record("Apple", "iPhone 12 mini", 6, 64, "mini.json"),
                ])
            findings, _ = audit(path)
            self.assertFalse(any(x[0] == "REVIEW_APPLE_RAM_DISAGREEMENT"
                                 for x in findings))


if __name__ == "__main__":
    unittest.main()
