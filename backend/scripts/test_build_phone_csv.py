"""Provenance and quarantine regression tests for the candidate CSV builder."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_phone_csv


class SourceDateConflictTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "upstream"
        self.source_dir = self.root / "data" / "smartphone" / "oppo" / "2022"
        self.source_dir.mkdir(parents=True)
        self.output = Path(self.temp.name) / "candidate.csv"

        # 500 synthetic fixtures satisfy the production size safety check.
        for number in range(500):
            self.write_source(f"control_{number}.json",
                              f"Control Model {number}", "2022-02-01")

    def write_source(self, filename, name, release_date, ram=8, storage=128):
        path = self.source_dir / filename
        path.write_text(json.dumps({
            "name": name, "release_date": release_date,
            "ram_gb": ram, "storage_gb": storage,
            "source_urls": [f"https://example.org/{filename}"],
        }), encoding="utf-8")
        return path

    def generate(self):
        with patch.object(build_phone_csv, "BRANDS", {"oppo": "Oppo"}):
            build_phone_csv.create_csv(self.root, self.output)

    def read_csv(self, path):
        with path.open(encoding="utf-8", newline="") as file:
            return list(csv.DictReader(file))

    def test_same_variant_disputed_date_preserves_both_source_records(self):
        self.write_source("disputed_early.json", "Oppo Find X5 Pro",
                          "2022-01-01", 8, 128)
        self.write_source("disputed_later.json", "Oppo Find X5 Pro",
                          "2022-03-14", 8, 128)
        self.write_source("different_variant.json", "Oppo Find X5 Pro",
                          "2022-03-14", 12, 256)
        self.generate()

        conflict_path = self.output.with_name("phones_release_date_conflicts.csv")
        conflicts = self.read_csv(conflict_path)
        self.assertEqual(len(conflicts), 3)
        self.assertEqual({x["candidate_release_date"] for x in conflicts},
                         {"2022-01-01", "2022-03-14"})
        self.assertEqual({x["upstream_path"].rsplit("/", 1)[-1]
                          for x in conflicts},
                         {"disputed_early.json", "disputed_later.json",
                          "different_variant.json"})
        self.assertTrue(all("2022-01-01; 2022-03-14" ==
                            x["conflicting_release_dates"] for x in conflicts))
        self.assertTrue(all(x["source_urls"] and
                            json.loads(x["source_urls"]) for x in conflicts))
        candidate = self.read_csv(self.output)
        self.assertEqual(len(candidate), 500)
        self.assertFalse(any(x["device"] == "Find X5 Pro" for x in candidate))

    def test_no_conflicts_overwrite_old_report_with_header_only(self):
        self.write_source("disputed_early.json", "Oppo Find X5 Pro",
                          "2022-01-01")
        self.write_source("disputed_later.json", "Oppo Find X5 Pro",
                          "2022-03-14")
        self.generate()
        self.assertTrue(self.read_csv(self.output.with_name(
            "phones_release_date_conflicts.csv")))

        (self.source_dir / "disputed_early.json").unlink()
        (self.source_dir / "disputed_later.json").unlink()
        self.generate()
        path = self.output.with_name("phones_release_date_conflicts.csv")
        self.assertTrue(path.exists())
        self.assertEqual(self.read_csv(path), [])


if __name__ == "__main__":
    unittest.main()
