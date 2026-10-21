"""No HTTP required: prevent fake and cross-model GSMArena Pixel images."""
import csv
import tempfile
import unittest
from pathlib import Path

from probe_pixel_product_images import (
    PAGES, filenames, probe, valid_jpeg_response,
)


class PixelProbeTests(unittest.TestCase):
    def test_exact_prefix_not_pro_or_fold(self):
        self.assertEqual(PAGES["Pixel 7"][0], "google_pixel_7-pictures-11903.php")
        self.assertNotIn("google-pixel-7-pro-1.jpg", filenames("pixel-7"))
        self.assertIn("google-pixel-8a-1.jpg", filenames("pixel-8a"))
        self.assertIn("google-pixel-10-pro-1.jpg", filenames("pixel-10-pro"))

    def test_bad_domain_never_requested(self):
        self.assertFalse(valid_jpeg_response(
            "https://not-gsmarena.example/vv/pics/google/google-pixel-7-1.jpg",
            opener=lambda req, timeout: self.fail("Network should not be touched")))

    def test_records_only_http_verified_pixel_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp, out = Path(tmp) / "catalog.csv", Path(tmp) / "photos.csv"
            with inp.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=("brand", "device"))
                writer.writeheader()
                for name in ("Pixel 6a", "Pixel 7", "Pixel 7 Pro", "Pixel 8A"):
                    writer.writerow({"brand": "Google", "device": name})
            actual = {
                "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-7-1.jpg",
                "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-8a-1.jpg",
            }
            result = probe(inp, out, validator=lambda url: url in actual)
            self.assertEqual({r["device"] for r in result}, {"Pixel 7", "Pixel 8A"})
            self.assertEqual(len(result), 2)
            self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
