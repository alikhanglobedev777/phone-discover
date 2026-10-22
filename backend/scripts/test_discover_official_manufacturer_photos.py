"""Offline exact manufacturer page + product image safety regression tests."""
import csv
import tempfile
import unittest
from pathlib import Path

from discover_official_manufacturer_photos import (
    ProductPage, exact_manufacturer_title, named_model_image, image_url_approved,
    inspect, scan, VALIDATION,
)


class ExampleFetcher:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, mime):
        return self.pages.get(url)


class OfficialSourceTests(unittest.TestCase):
    def test_exact_page_title_must_not_mix_editions(self):
        self.assertTrue(exact_manufacturer_title(
            "Infinix - NOTE 40 Pro - Pakistan", "Infinix", "Note 40 Pro"))
        self.assertFalse(exact_manufacturer_title(
            "Infinix - NOTE 40 Pro 5G - Pakistan", "Infinix", "Note 40 Pro"))
        self.assertFalse(exact_manufacturer_title(
            "Infinix - NOTE 40 Pro+ - Pakistan", "Infinix", "Note 40 Pro"))
        self.assertTrue(exact_manufacturer_title(
            "Xiaomi 13 Pro | Official product", "Xiaomi", "13 Pro"))

    def test_only_exact_model_image_names_not_logos(self):
        self.assertTrue(named_model_image("NOTE 40 Pro", "Infinix", "Note 40 Pro"))
        self.assertTrue(named_model_image(
            "Infinix Note 40 Pro back", "Infinix", "Note 40 Pro"))
        self.assertFalse(named_model_image(
            "Infinix Note 40 Pro 5G", "Infinix", "Note 40 Pro"))
        self.assertFalse(named_model_image("Infinix", "Infinix", "Note 40 Pro"))
        self.assertFalse(named_model_image("Note 40", "Infinix", "Note 40 Pro"))

    def test_manufacturer_cdn_domain_is_strict(self):
        self.assertTrue(image_url_approved(
            "Infinix", "https://cdn.infinixmobility.com/phones/note40pro.png"))
        self.assertFalse(image_url_approved(
            "Infinix", "https://infinixmobility.com.bad-example.org/phones/p.png"))
        self.assertFalse(image_url_approved(
            "Motorola", "https://infinixmobility.com/phones/motorola.png"))
        self.assertFalse(image_url_approved(
            "Motorola", "http://www.motorola.com/media/g84.png"))

    def test_records_only_exact_verified_official_product_photo(self):
        page_url = "https://pk.infinixmobility.com/note-40-pro"
        png = "https://pk.infinixmobility.com/static/note-40-pro.png"
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Path(tmp) / "gap.csv"
            out = Path(tmp) / "images.csv"
            catalog.write_text(
                "brand,device\nInfinix,Note 40 Pro\nInfinix,Note 40\n",
                encoding="utf-8")
            page = """<title>Infinix - NOTE 40 Pro - Pakistan</title>
            <img src="https://pk.infinixmobility.com/logo.png" alt="Infinix">
            <img src="/static/note-40-pro.png" alt="NOTE 40 Pro">"""
            fetcher = ExampleFetcher({page_url: page, png: b"\x89PNG\r\n\x1a\nvalid"})
            result = scan(catalog, out, "Infinix", parts=1, fetcher=fetcher)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["device"], "Note 40 Pro")
            self.assertEqual(result[0]["image_url"], png)
            self.assertEqual(result[0]["source_url"], page_url)
            self.assertEqual(result[0]["source_validation"], VALIDATION)
            with out.open(encoding="utf-8", newline="") as f:
                self.assertEqual(len(list(csv.DictReader(f))), 1)

    def test_suspicious_page_does_not_match(self):
        p = ProductPage()
        p.feed("<title>Infinix - NOTE 40 Pro 5G - Pakistan</title>")
        self.assertFalse(any(exact_manufacturer_title(x, "Infinix", "Note 40 Pro")
                             for x in p.titles))


if __name__ == "__main__":
    unittest.main()
