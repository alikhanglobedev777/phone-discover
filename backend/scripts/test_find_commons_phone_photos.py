"""Regression tests for exact-model Wikimedia photo discovery; no live API requests."""
import unittest
from unittest.mock import patch

import find_commons_phone_photos as photos


class CommonsPhotoTests(unittest.TestCase):
    def test_exact_model_and_brand_required(self):
        exact = {"label": "iPhone 12", "description": "smartphone by Apple Inc."}
        self.assertTrue(photos.exact_phone_candidate(exact, "Apple", "iPhone 12"))
        self.assertFalse(photos.exact_phone_candidate(exact, "Apple", "iPhone 12 mini"))
        self.assertFalse(photos.exact_phone_candidate(exact, "Samsung", "iPhone 12"))
        self.assertFalse(photos.exact_phone_candidate(
            {"label": "Galaxy A90", "description": "model of transport"}, "Samsung", "Galaxy A90"))

    def test_reject_unlicensed_photo(self):
        datasets = [
            {"search": [{"id": "Q123", "label": "iPhone 12",
                         "description": "Apple smartphone"}]},
            {"entities": {"Q123": {"claims": {
                "P18": [{"mainsnak": {"datavalue": {"value": "iPhone12.jpg"}}}]
            }}}},
            {"query": {"pages": {"20": {"imageinfo": [{
                "url": "https://upload.wikimedia.org/example/iPhone12.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:iPhone12.jpg",
                "mime": "image/jpeg",
                "extmetadata": {"LicenseShortName": {"value": "All rights reserved"}}
            }]}}}},
        ]
        with patch.object(photos, "fetch_json", side_effect=datasets):
            self.assertIsNone(photos.commons_photo("Apple", "iPhone 12"))

    def test_accept_exact_licensed_photo_with_attribution(self):
        datasets = [
            {"search": [{"id": "Q123", "label": "iPhone 12",
                         "description": "Apple smartphone"}]},
            {"entities": {"Q123": {"claims": {
                "P18": [{"mainsnak": {"datavalue": {"value": "iPhone12.jpg"}}}]
            }}}},
            {"query": {"pages": {"20": {"imageinfo": [{
                "url": "https://upload.wikimedia.org/example/iPhone12.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:iPhone12.jpg",
                "mime": "image/jpeg",
                "extmetadata": {
                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
                    "Artist": {"value": "<a>Example photographer</a>"},
                }
            }]}}}},
        ]
        with patch.object(photos, "fetch_json", side_effect=datasets):
            image = photos.commons_photo("Apple", "iPhone 12")
        self.assertEqual(image["wikidata_id"], "Q123")
        self.assertEqual(image["image_license"], "CC BY-SA 4.0")
        self.assertEqual(image["image_credit"], "Example photographer")


if __name__ == "__main__":
    unittest.main()
