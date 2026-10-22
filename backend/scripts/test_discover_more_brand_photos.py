"""Check stricter second-pass image recovery never substitutes another model."""
import csv
import tempfile
import unittest
from pathlib import Path

from discover_more_brand_photos import (
    additional_roots, is_exact_image_path, scan, second_pass_candidates,
)
from discover_missing_brand_images import BRANDS, COLUMNS, VALIDATION
from merge_more_brand_photos import merge


class MoreBrandPhotosTests(unittest.TestCase):
    def test_motorola_full_model_extra_root(self):
        self.assertIn("motorola-moto-g84-5g", additional_roots("Motorola", "G84 5G"))
        self.assertNotIn("motorola-moto-g84", additional_roots("Motorola", "G84 5G"))
        self.assertNotIn("motorola-edge-50-pro", additional_roots("Motorola", "Edge 50"))

    def test_never_match_pro_versus_base_or_4g_versus_5g(self):
        url = "https://fdn2.gsmarena.com/vv/pics/infinix/infinix-note-40-pro-3.jpg"
        self.assertTrue(is_exact_image_path(url, "Infinix", "Note 40 Pro"))
        self.assertFalse(is_exact_image_path(url, "Infinix", "Note 40"))
        self.assertFalse(is_exact_image_path(url, "Infinix", "Note 40 Pro 5G"))
        url2 = "https://fdn2.gsmarena.com/vv/pics/samsung/samsung-galaxy-a15-5g-4.jpg"
        self.assertFalse(is_exact_image_path(url2, "Samsung", "Galaxy A15 4G"))
        self.assertFalse(is_exact_image_path(
            url2.replace("fdn2.gsmarena.com", "attacker.gsmarena.com"),
            "Samsung", "Galaxy A15 5G"))

    def test_only_verified_missing_models_are_emitted(self):
        with tempfile.TemporaryDirectory() as t:
            path, out = Path(t) / "gap.csv", Path(t) / "more.csv"
            path.write_text(
                "brand,device\nMotorola,G84 5G\nMotorola,Edge 50\n"
                "Motorola,Edge 50 Pro\n", encoding="utf-8")
            selected = "https://fdn2.gsmarena.com/vv/pics/motorola/motorola-moto-g84-5g-3.jpg"
            data = scan(path, out, "Motorola", parts=1,
                        checker=lambda url: url == selected, pace=0)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["device"], "G84 5G")
            with out.open(encoding="utf-8", newline="") as f:
                self.assertEqual(len(list(csv.DictReader(f))), 1)

    def test_merge_rejects_cross_model_picture_and_accepts_exact(self):
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t)
            gaps = folder / "gap.csv"
            gaps.write_text("brand,device\nMotorola,G84 5G\n"
                            "Infinix,Note 40 Pro\n", encoding="utf-8")
            files = folder / "shards"
            files.mkdir()
            for brand in BRANDS:
                file = files / (brand.lower() + "-0.csv")
                with file.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=COLUMNS)
                    writer.writeheader()
                    if brand == "Motorola":
                        url = "https://fdn2.gsmarena.com/vv/pics/motorola/motorola-moto-g84-5g-3.jpg"
                        writer.writerow({
                            "brand": brand, "device": "G84 5G",
                            "image_url": url, "source_url": url,
                            "publisher": "GSMArena", "source_validation": VALIDATION,
                        })
            rows = merge(files, gaps, folder / "output.csv", parts=1)
            self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
