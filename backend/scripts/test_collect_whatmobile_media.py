"""No network: test URL candidate generation and independent image checks."""
import io
import unittest
from unittest.mock import patch

from collect_whatmobile_media import candidate_paths, photo_is_accessible


class ImageResponse:
    def __init__(self, mime, signature):
        self.headers = {"Content-Type": mime}
        self.signature = signature

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return "https://www.whatmobile.com.pk/admin/images/Xiaomi/Xiaomi12SPro-b.jpg"

    def read(self, n):
        return self.signature[:n]


class PermissiveFetcher:
    def can_fetch(self, url):
        return True


class CollectorTests(unittest.TestCase):
    def test_page_candidates_preserve_exact_model(self):
        self.assertEqual(
            candidate_paths("Xiaomi", "12S Pro"),
            ["https://www.whatmobile.com.pk/Xiaomi_12S-Pro"],
        )
        self.assertEqual(
            candidate_paths("Xiaomi", "12 Pro (Dimensity)"),
            ["https://www.whatmobile.com.pk/Xiaomi_12-Pro-%28Dimensity%29",
             "https://www.whatmobile.com.pk/Xiaomi_12-Pro-Dimensity"],
        )

    @patch("collect_whatmobile_media.urlopen")
    def test_content_type_and_image_magic(self, open_url):
        src = "https://www.whatmobile.com.pk/admin/images/Xiaomi/Xiaomi12SPro-b.jpg"
        open_url.return_value = ImageResponse("image/jpeg", b"\xff\xd8\xff\x00\x00")
        self.assertTrue(photo_is_accessible(src, PermissiveFetcher()))
        open_url.return_value = ImageResponse("text/html", b"\xff\xd8\xff\x00\x00")
        self.assertFalse(photo_is_accessible(src, PermissiveFetcher()))
        open_url.return_value = ImageResponse("image/jpeg", b"<html>")
        self.assertFalse(photo_is_accessible(src, PermissiveFetcher()))

    def test_never_accept_other_host(self):
        self.assertFalse(photo_is_accessible(
            "https://priceoye.pk/admin/images/phone.jpg", PermissiveFetcher()))
        self.assertFalse(photo_is_accessible(
            "https://www.whatmobile.com.pk/other/phone.jpg", PermissiveFetcher()))


if __name__ == "__main__":
    unittest.main()
