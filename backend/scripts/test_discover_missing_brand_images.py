"""Offline regression tests for the 10-brand image crawler and strict merge."""
import csv
import tempfile
import unittest
from pathlib import Path

from discover_missing_brand_images import (
    BRANDS, COLUMNS, VALIDATION, model_image_urls, model_slug,
    root_names, scan, valid_source_url,
)
from merge_verified_brand_images import merge


def make_row(brand, name, url):
    return {
        "brand": brand, "device": name, "image_url": url,
        "publisher": "GSMArena", "source_url": url,
        "source_validation": VALIDATION,
    }


class BrandPhotoTests(unittest.TestCase):
    def test_do_not_mix_pro_max_ultra_and_base(self):
        pixel = list(model_image_urls("Google", "Pixel 8"))
        self.assertNotIn(
            "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-8-pro-1.jpg", pixel)
        self.assertIn(
            "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-8-1.jpg", pixel)
        self.assertNotIn(
            "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-15-pro-max-1.jpg",
            list(model_image_urls("Apple", "iPhone 15 Pro")))
        self.assertNotIn(
            "https://fdn2.gsmarena.com/vv/pics/motorola/motorola-edge-50-pro-1.jpg",
            list(model_image_urls("Motorola", "Edge 50")))

    def test_exact_authorized_hosts_and_model_filenames(self):
        correct = "https://fdn2.gsmarena.com/vv/pics/infinix/infinix-hot-40-pro-1.jpg"
        self.assertTrue(valid_source_url(correct, "Infinix", "Hot 40 Pro"))
        self.assertFalse(valid_source_url(correct, "Infinix", "Hot 40"))
        self.assertFalse(valid_source_url(
            "https://fdn2.gsmarena.com.evil.example/vv/pics/infinix/infinix-hot-40-pro-1.jpg",
            "Infinix", "Hot 40 Pro"))
        self.assertFalse(valid_source_url(
            "https://fdn2.gsmarena.com/vv/pics/infinix/infinix-hot-40-pro-1.jpg?other=1",
            "Infinix", "Hot 40 Pro"))

    def test_make_valid_motorola_name_roots(self):
        self.assertEqual(root_names("Motorola", "Moto G54"),
                         ["motorola-moto-g54"])
        self.assertIn("motorola-edge-50-pro", root_names("Motorola", "Edge 50 Pro"))
        self.assertEqual(model_slug("Note 40 Pro+"), "note-40-pro-plus")

    def test_scan_keeps_only_verifiably_present_jpegs(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "phones.csv"
            out = Path(tmp) / "photos.csv"
            source.write_text("brand,device\nInfinix,Hot 40 Pro\nInfinix,Hot 40\n"
                              "Motorola,Moto G54\n", encoding="utf-8")
            image = "https://fdn2.gsmarena.com/vv/pics/infinix/infinix-hot-40-pro-1.jpg"
            rows = scan(source, out, "Infinix", parts=1, checker=lambda url: url == image,
                        pace=0)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["device"], "Hot 40 Pro")
            self.assertTrue(out.exists())

    def test_merge_quarantines_shared_image_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "phones.csv"
            source.write_text("brand,device\nInfinix,Hot 40 Pro\n"
                              "Motorola,Moto G54\n", encoding="utf-8")
            shard_dir = root / "shards"
            shard_dir.mkdir()
            for brand in BRANDS:
                with (shard_dir / f"{brand.lower()}-0.csv").open(
                    "w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=COLUMNS)
                    writer.writeheader()
                    if brand == "Infinix":
                        writer.writerow(make_row("Infinix", "Hot 40 Pro",
                            "https://fdn2.gsmarena.com/vv/pics/infinix/infinix-hot-40-pro-1.jpg"))
                    if brand == "Motorola":
                        writer.writerow(make_row("Motorola", "Moto G54",
                            "https://fdn2.gsmarena.com/vv/pics/motorola/motorola-moto-g54-1.jpg"))
            rows = merge(shard_dir, source, root / "merged.csv", parts=1)
            self.assertEqual(len(rows), 2)

    def test_no_guessed_images_imported_when_no_jpeg_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Path(tmp) / "phones.csv"
            catalog.write_text("brand,device\nMotorola,Moto G54\n", encoding="utf-8")
            output = Path(tmp) / "photos.csv"
            rows = scan(catalog, output, "Motorola", parts=1, checker=lambda url: False,
                        pace=0)
            self.assertEqual(rows, [])
            with output.open(encoding="utf-8", newline="") as f:
                self.assertEqual(list(csv.DictReader(f)), [])


if __name__ == "__main__":
    unittest.main()
