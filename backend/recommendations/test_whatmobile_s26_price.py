"""Regression: WhatMobile puts a comma between storage and 'Built-in'."""

from unittest.mock import patch

from django.test import SimpleTestCase

from .phone_options import extract_memory_pairs
from .source_research import parse_product, research_source_pages, research_urls


URL = "https://www.whatmobile.com.pk/Samsung_Galaxy-S26-Ultra"
CRITERIA = {"brand": "samsung", "device_query": "Galaxy S26 Ultra", "condition": "box_pack"}
# Real WhatMobile text format on its S26 Ultra specifications page.
HTML = """
<h1>Samsung Galaxy S26 Ultra</h1>
<div>Rs. 449,999</div>
<table>
  <tr><th class="specs-subHeading">Built-in</th>
      <td class="specs-value">256GB, Built-in, 12GB RAM, UFS 4.X</td></tr>
  <tr><th class="specs-subHeading">Colors</th>
      <td class="specs-value">Cobalt Violet, Sky Blue, Black, White, Silver Shadow, Pink Gold</td></tr>
  <tr><th class="specs-subHeading">Capacity</th>
      <td class="specs-value">Li-ion 5000 mAh</td></tr>
</table>
"""


class WhatMobileS26PriceTests(SimpleTestCase):
    def test_price_accepts_actual_comma_built_in_format(self):
        phone = parse_product(HTML, URL, "Samsung")
        self.assertEqual(phone["name"], "Galaxy S26 Ultra")
        self.assertEqual((phone["ram_gb"], phone["storage_gb"]), (12, 256))
        self.assertEqual(phone["price_min_pkr"], "449999")

    def test_whatmobile_option_extraction_accepts_same_format(self):
        self.assertEqual(extract_memory_pairs("256GB, Built-in, 12GB RAM, UFS 4.X"), [(12, 256)])

    @patch("recommendations.source_research._fetch", return_value=HTML)
    def test_direct_source_fallback_is_priced_not_specs_only(self, fetch):
        research = research_source_pages(CRITERIA)
        self.assertEqual(research["status"], "grounded_preview")
        phone = research["document"]["phones"][0]
        self.assertEqual(phone["price_min_pkr"], "449999")
        self.assertEqual(phone["available_variants"], [{"ram_gb": 12, "storage_gb": 256}])
        self.assertIn("Cobalt Violet", phone["available_colors"])
        fetch.assert_called_once_with(URL)

    @patch("recommendations.source_research._fetch", return_value=HTML)
    def test_tavily_whatmobile_link_is_importable(self, fetch):
        research = research_urls(CRITERIA, [{"url": URL}], provider="tavily")
        self.assertEqual(research["status"], "grounded_preview")
        self.assertEqual(research["document"]["phones"][0]["price_min_pkr"], "449999")

    def test_multi_storage_and_expected_price_still_rejected(self):
        multi = HTML.replace("256GB, Built-in", "256GB/512GB, Built-in")
        with self.assertRaises(ValueError):
            parse_product(multi, URL, "Samsung")
        expected = HTML.replace("Rs. 449,999", "Rs. Coming Soon (Expected Rs. 449,999)")
        with self.assertRaises(ValueError):
            parse_product(expected, URL, "Samsung")
