"""Exact-model specification sources must not become unverified price offers."""

from unittest.mock import patch

from django.test import SimpleTestCase

from .source_research import research_source_pages, research_urls


SAMPLE = """
<h1>Vivo X90s</h1>
<span>Rs. Coming Soon (Expected Rs. 159,999)</span>
<table><tr><th class="specs-subHeading">Chipset</th>
<td class="specs-value">Mediatek Dimensity 9200+</td></tr></table>
"""


class SpecificationsOnlyTests(SimpleTestCase):
    criteria = {"brand": "vivo", "device_query": "X90S", "condition": "box_pack"}

    @patch("recommendations.source_research._fetch", return_value=SAMPLE)
    def test_tavily_miss_returns_correct_model_specs_without_price(self, fetch):
        result = research_urls(self.criteria, [], provider="tavily")
        self.assertEqual(result["status"], "specifications_only")
        self.assertEqual(result["document"]["phones"], [])
        self.assertEqual(result["results"], [])
        self.assertEqual(result["sources"][0]["url"], "https://www.whatmobile.com.pk/Vivo_X90s")
        self.assertIn("no price was saved", result["notice"])
        self.assertIn("Mediatek Dimensity 9200+", result["notice"])
        fetch.assert_called_once_with("https://www.whatmobile.com.pk/Vivo_X90s")

    @patch("recommendations.source_research._fetch", return_value=SAMPLE)
    def test_source_pages_fallback_preserves_unpriced_specs(self, fetch):
        result = research_source_pages(self.criteria)
        self.assertEqual(result["status"], "specifications_only")
        self.assertEqual(result["document"]["phones"], [])
        self.assertFalse(result["results"])

    @patch("recommendations.source_research._fetch", return_value="<h1>Vivo V80 Lite</h1>")
    def test_sibling_phone_cannot_be_presented_as_requested_model(self, fetch):
        result = research_urls(self.criteria, [], provider="tavily")
        self.assertEqual(result["status"], "no_sources")
        self.assertEqual(result["sources"], [])

    @patch("recommendations.source_research._fetch")
    def test_no_model_query_does_not_fetch_a_guessed_spec_page(self, fetch):
        result = research_urls({"brand": "vivo"}, [], provider="tavily")
        self.assertEqual(result["status"], "no_sources")
        fetch.assert_not_called()
