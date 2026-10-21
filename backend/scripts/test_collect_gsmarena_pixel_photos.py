"""Exact Google Pixel photo identity regression tests. No live HTTP requests."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from collect_gsmarena_pixel_photos import (
    collect, exact_picture_page, Page, safe_picture_url,
)


class LocalFetcher:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url):
        return self.pages.get(url)


class GooglePixelPhotoTests(unittest.TestCase):
    def test_exact_google_pixel_image_url_required(self):
        self.assertTrue(safe_picture_url(
            "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-9-1.jpg", "pixel_9"
        ))
        self.assertFalse(safe_picture_url(
            "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-9-pro-1.jpg", "pixel_9"
        ))
        self.assertFalse(safe_picture_url(
            "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-9-1.jpg", "pixel_9_pro"
        ))
        self.assertFalse(safe_picture_url(
            "https://fdn2.gsmarena.com/vv/pics/samsung/google-pixel-9-1.jpg", "pixel_9"
        ))
        self.assertFalse(safe_picture_url(
            "https://evil.example/vv/pics/google/google-pixel-9-1.jpg", "pixel_9"
        ))

    def test_gallery_page_must_have_exact_model_title(self):
        p = Page()
        p.feed("<h1>Google Pixel 9 Pro pictures</h1>")
        self.assertFalse(exact_picture_page(p, "Pixel 9"))
        self.assertTrue(exact_picture_page(p, "Pixel 9 Pro"))

    def test_full_scan_only_collects_exact_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "catalog.csv"
            output_path = Path(tmp) / "pixels.csv"
            with input_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=("brand", "device"))
                w.writeheader()
                w.writerow({"brand": "Google", "device": "Pixel 9"})
                w.writerow({"brand": "Google", "device": "Pixel 9 Pro"})
                w.writerow({"brand": "Samsung", "device": "Galaxy A55"})
            index = """<a href="/google_pixel_9-13219.php">Pixel 9</a>
                       <a href="/google_pixel_9_pro-13218.php">Pixel 9 Pro</a>
                       <a href="/google_pixel_9_pro_xl-13217.php">Pixel 9 Pro XL</a>"""
            pages = {
                "https://www.gsmarena.com/google-phones-107.php": index,
                "https://www.gsmarena.com/google_pixel_9-pictures-13219.php":
                    '<h1>Google Pixel 9 pictures</h1>'
                    '<img src="https://fdn2.gsmarena.com/vv/pics/google/google-pixel-9-1.jpg" alt="Google Pixel 9">'
                    '<img src="https://fdn2.gsmarena.com/vv/pics/google/google-pixel-9-pro-1.jpg" alt="Google Pixel 9 Pro">',
                "https://www.gsmarena.com/google_pixel_9_pro-pictures-13218.php":
                    '<h1>Google Pixel 9 Pro pictures</h1>'
                    '<img src="https://fdn2.gsmarena.com/vv/pics/google/google-pixel-9-pro-1.jpg" alt="Google Pixel 9 Pro">',
            }
            data = collect(input_path, output_path, LocalFetcher(pages))
            self.assertEqual(len(data), 2)
            by_model = {item["device"]: json.loads(item["image_urls"]) for item in data}
            self.assertEqual(by_model["Pixel 9"],
                             ["https://fdn2.gsmarena.com/vv/pics/google/google-pixel-9-1.jpg"])
            self.assertEqual(by_model["Pixel 9 Pro"],
                             ["https://fdn2.gsmarena.com/vv/pics/google/google-pixel-9-pro-1.jpg"])
            self.assertTrue(output_path.exists())

    def test_no_index_does_not_create_empty_success_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "catalog.csv"
            output_path = Path(tmp) / "no.csv"
            input_path.write_text("brand,device\nGoogle,Pixel 9\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "not accessible"):
                collect(input_path, output_path, LocalFetcher({}))
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
