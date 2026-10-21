"""Unit tests for strict retail product-image source matching (no HTTP calls)."""
import unittest

from discover_retailer_phone_images import (
    Page, approved_host, identity, image_from_page, page_paths, same_model,
)


class RetailerImageDiscoveryTests(unittest.TestCase):
    def test_dont_confuse_pro_or_ultra(self):
        self.assertTrue(same_model("Xiaomi 12S Ultra", "Xiaomi", "12S Ultra"))
        self.assertFalse(same_model("Xiaomi 12S Ultra", "Xiaomi", "12S"))
        self.assertFalse(same_model("Xiaomi 12S Pro", "Xiaomi", "12S Ultra"))
        self.assertFalse(same_model("Samsung Galaxy S23 Ultra", "Samsung", "Galaxy S23"))
        self.assertTrue(same_model(
            "Samsung Galaxy S23 Ultra Price in Pakistan", "Samsung", "Galaxy S23 Ultra"))
        self.assertFalse(same_model(
            "Apple iPhone 12 Mini Price in Pakistan", "Apple", "iPhone 12"))

    def test_whatmobile_photo_and_colors(self):
        page = Page()
        page.feed("""<html><h1>Xiaomi 12S Ultra</h1><div>
        <img src="/admin/images/Xiaomi/Xiaomi12SUltra-b.jpg"
          alt="Xiaomi 12S Ultra Mobile Price in Pakistan" />
        <img src="/admin/images/Xiaomi/Xiaomi12SPro-b.jpg"
          alt="Xiaomi 12S Pro Mobile Price in Pakistan" />
        <img src="/images/logo.png" alt="brand logo" />
        </div><table><tr><td>Colors</td><td>Black, Dark Green</td></tr></table></html>""")
        url = image_from_page(page, "https://www.whatmobile.com.pk/Xiaomi_12S-Ultra",
                              "Xiaomi", "12S Ultra", "WhatMobile")
        self.assertEqual(url,
                         "https://www.whatmobile.com.pk/admin/images/Xiaomi/Xiaomi12SUltra-b.jpg")
        self.assertEqual(page.first_color_names(), "Black, Dark Green")
        self.assertIsNone(image_from_page(page,
             "https://www.whatmobile.com.pk/Xiaomi_12S-Ultra", "Xiaomi", "12S Pro", "WhatMobile"))

    def test_priceoye_og_image_with_exact_page_title(self):
        page = Page()
        page.feed("""<title>Xiaomi 12S Ultra Price in Pakistan 2026 | Priceoye</title>
        <h1>Xiaomi 12S Ultra</h1>
        <meta property="og:image" content="https://images.priceoye.pk/product/12s-ultra.webp">
        <img alt="slider-image" src="https://unrelated.com/im.jpg"/>""")
        url = image_from_page(page, "https://priceoye.pk/mobiles/xiaomi/xiaomi-12s-ultra",
                              "Xiaomi", "12S Ultra", "PriceOye")
        self.assertEqual(url, "https://images.priceoye.pk/product/12s-ultra.webp")
        self.assertIsNone(image_from_page(page, "https://priceoye.pk/mobiles/xiaomi/xiaomi-12s-ultra",
                              "Xiaomi", "12S", "PriceOye"))

    def test_photo_hosts_are_restricted(self):
        self.assertFalse(approved_host("https://priceoye.pk.bad-domain.com/foo.jpg", "PriceOye"))
        self.assertFalse(approved_host("http://priceoye.pk/foo.jpg", "PriceOye"))
        self.assertTrue(approved_host("https://images.priceoye.pk/foo.jpg", "PriceOye"))
        self.assertFalse(approved_host("https://upload.wikimedia.org/ok.jpg", "PriceOye"))
        self.assertTrue(approved_host("https://www.whatmobile.com.pk/admin/images/x.jpg", "WhatMobile"))

    def test_canonical_urls_not_search_engine_results(self):
        sites = dict(page_paths("Xiaomi", "12S Ultra"))
        self.assertEqual(sites["WhatMobile"], "https://www.whatmobile.com.pk/Xiaomi_12S-Ultra")
        self.assertEqual(sites["PriceOye"], "https://priceoye.pk/mobiles/xiaomi/xiaomi-12s-ultra")


if __name__ == "__main__":
    unittest.main()
