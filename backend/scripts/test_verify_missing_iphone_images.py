"""Ensure exact iPhone identity, Pro/Max isolation, and SE year distinction."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from verify_missing_iphone_images import (
    MODELS, VERIFICATION, sources_for, verify, valid_apple_jpeg_response,
)


class AppleGalleryTests(unittest.TestCase):
    def test_every_missing_canonical_iphone_is_explicitly_mapped(self):
        names = {
            name for _, _, aliases in MODELS.values() for name in aliases
        }
        self.assertEqual(len(names), 14)
        self.assertIn("iPhone 16 Pro (256GB SG)", names)
        self.assertIn("iPhone 14 Pro Max UW", names)
        self.assertIn("iPhone SE (3rd generation)", names)
        self.assertNotIn("iPhone 16 Pro Max (1TB SG)", names)  # separately reused

    def test_pro_plus_max_and_se_year_not_interchangeable(self):
        p = list(sources_for("iPhone 16"))
        self.assertTrue(any("apple-iphone-16-1.jpg" in u for u in p))
        self.assertFalse(any("iphone-16-pro" in u for u in p))
        self.assertFalse(any("iphone-16-plus" in u for u in p))
        p2 = list(sources_for("iPhone SE (2020)"))
        p3 = list(sources_for("iPhone SE (2022)"))
        self.assertTrue(any("iphone-se-2020" in u for u in p2))
        self.assertTrue(any("iphone-se-2022" in u for u in p3))
        self.assertTrue(set(p2).isdisjoint(set(p3)))

    def test_apple_jpeg_validator_requires_real_apple_photo_response(self):
        image = "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-16-1.jpg"

        class DummyResponse:
            headers = {"Content-Type": "image/jpeg"}
            def geturl(self):
                return image
            def read(self, size):
                return bytes.fromhex("ffd8ff") + bytes(5000)
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False

        self.assertTrue(valid_apple_jpeg_response(
            image, opener=lambda req, timeout: DummyResponse()))
        self.assertFalse(valid_apple_jpeg_response(
            image.replace("/apple/", "/google/"),
            opener=lambda req, timeout: self.fail("wrong manufacturer must be blocked")))

    def test_only_http_verified_images_are_published_and_grouped_by_model(self):
        with tempfile.TemporaryDirectory() as t:
            catalog = Path(t) / "gap.csv"
            manifest = Path(t) / "verified.csv"
            catalog.write_text(
                "brand,device\n"
                "Apple,iPhone 16 (256GB SG)\n"
                "Apple,iPhone 16 (512GB USA)\n"
                "Apple,iPhone 16 Pro (1TB SG)\n"
                "Apple,iPhone SE (3rd generation)\n"
                "Google,Pixel 9\n", encoding="utf-8")
            confirmed = {
                "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-16-1.jpg",
                "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-16-2.jpg",
                "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-se-2022-0.jpg",
            }
            rows = verify(catalog, manifest, checker=lambda url: url in confirmed)
            self.assertEqual(len(rows), 3)
            self.assertEqual({r["device"] for r in rows}, {
                "iPhone 16 (256GB SG)", "iPhone 16 (512GB USA)",
                "iPhone SE (3rd generation)",
            })
            self.assertTrue(all(r["source_validation"] == VERIFICATION for r in rows))
            self.assertEqual(json.loads(rows[0]["image_urls"]), [
                "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-16-1.jpg",
                "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-16-2.jpg",
            ])
            with manifest.open(encoding="utf-8", newline="") as f:
                self.assertEqual(len(list(csv.DictReader(f))), 3)

    def test_no_image_response_does_not_publish_guessed_urls(self):
        with tempfile.TemporaryDirectory() as t:
            catalog = Path(t) / "gap.csv"
            manifest = Path(t) / "verified.csv"
            catalog.write_text("brand,device\nApple,iPhone 12 UW\n", encoding="utf-8")
            self.assertEqual(verify(catalog, manifest,
                                    checker=lambda url: False), [])
            with manifest.open(encoding="utf-8", newline="") as f:
                self.assertEqual(list(csv.DictReader(f)), [])


if __name__ == "__main__":
    unittest.main()
