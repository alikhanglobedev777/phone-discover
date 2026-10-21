"""Regression tests for source-preserving, create-only catalog preparation."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from prepare_production_catalog import FIELDS, clean_name, prepare, stable_slug

BRANDS = ["Apple", "Samsung", "Google", "Oppo", "Vivo",
          "Xiaomi", "Motorola", "Infinix", "Tecno", "Itel"]


class ProductionCatalogTests(unittest.TestCase):
    def test_plus_slugs_and_memory_suffixes(self):
        self.assertEqual(stable_slug("Samsung", "Galaxy S22+ 5G"),
                         "samsung-galaxy-s22-plus-5g")
        self.assertNotEqual(stable_slug("Samsung", "Galaxy S22+ 5G"),
                            stable_slug("Samsung", "Galaxy S22 5G"))
        self.assertEqual(clean_name("iPhone 12 128GB", 4, 128), "iPhone 12")
        self.assertEqual(clean_name("Galaxy A04 (4GB RAM + 128GB)", 4, 128),
                         "Galaxy A04")
        self.assertIsNone(clean_name("Galaxy A04 (4GB RAM + 128GB)", 8, 128))
        self.assertIsNone(clean_name(
            "Galaxy A04 Global Dual SIM TD-LTE 128GB", 4, 128))

    def test_conflicts_leave_dates_unknown_without_losing_variants(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidates = root / "candidates.csv"
            conflicts = root / "conflicts.csv"
            output = root / "import.csv"
            with candidates.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
                for brand in BRANDS:
                    for n in range(55):
                        writer.writerow({
                            "brand": brand, "device": f"Candidate {brand} {n}",
                            "release_date": "2023-05-04", "ram_gb": 8, "storage_gb": 128,
                            "source_urls": json.dumps(["https://example.org/datasheet"]),
                            "colors": "[]"})
                writer.writerow({
                    "brand": "Oppo", "device": "Find X5 Pro 128GB",
                    "release_date": "2022-01-01", "ram_gb": 8, "storage_gb": 128,
                    "source_urls": json.dumps(["https://example.org/early"]),
                    "colors": "[]"})
            with conflicts.open("w", newline="", encoding="utf-8") as f:
                columns = ["brand", "device", "candidate_release_date", "ram_gb",
                           "storage_gb", "source_urls", "upstream_path"]
                writer = csv.DictWriter(f, fieldnames=columns)
                writer.writeheader()
                writer.writerow({
                    "brand": "Oppo", "device": "Find X5 Pro",
                    "candidate_release_date": "2022-03-14",
                    "ram_gb": 12, "storage_gb": 256,
                    "source_urls": json.dumps(["https://example.org/later"])})
            rows = prepare(candidates, conflicts, output)
            variants = [r for r in rows
                        if r["brand"] == "Oppo" and r["device"] == "Find X5 Pro"]
            self.assertEqual(len(variants), 2)
            self.assertTrue(all(r["release_date"] == "" for r in variants))
            self.assertEqual(
                len({(r["brand"], r["device"]) for r in rows}), 551)
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
