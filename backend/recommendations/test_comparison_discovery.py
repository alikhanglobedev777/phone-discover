"""Comparison exact-model lookup and web-source fallback regression tests."""

from unittest.mock import MagicMock, Mock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from .model_identity import matches_phone_model
from .source_research import _whatmobile_exact_url, research_urls
from .views import ComparisonPhoneLookupView


S24_HTML = """
<h1>Samsung Galaxy S24 Ultra</h1>
<div>Rs. 434,999</div>
<table>
<tr><th class="specs-subHeading">Built-in</th>
<td class="specs-value">256GB Built-in, 12GB RAM, UFS 4.0</td></tr>
<tr><th class="specs-subHeading">Capacity</th>
<td class="specs-value">5000 mAh</td></tr>
</table>
"""


class ComparisonDiscoveryTests(SimpleTestCase):
    def test_samsung_galaxy_alias_is_exact(self):
        self.assertTrue(matches_phone_model("samsung s24 ultra", "Samsung", "Galaxy S24 Ultra"))
        self.assertTrue(matches_phone_model("Samsung Galaxy S24 Ultra 12GB 256GB", "Samsung", "Galaxy S24 Ultra"))
        self.assertFalse(matches_phone_model("samsung s24 ultra", "Samsung", "Galaxy S24 Plus"))
        self.assertFalse(matches_phone_model("samsung s24", "Samsung", "Galaxy S24 Ultra"))

    def test_whatmobile_exact_url(self):
        for query in ("samsung s24 ultra", "samsung galaxy s24 ultra", "Galaxy S24 Ultra"):
            self.assertEqual(
                _whatmobile_exact_url({"brand": "samsung", "device_query": query})[0],
                "https://www.whatmobile.com.pk/Samsung_Galaxy-S24-Ultra",
            )

    @patch("recommendations.source_research._fetch", return_value=S24_HTML)
    def test_search_rejects_sibling_but_accepts_exact_product_page(self, fetch):
        criteria = {"brand": "samsung", "device_query": "Galaxy S24 Ultra",
                    "comparison_target": "samsung s24 ultra"}
        urls = [
            {"url": "https://www.whatmobile.com.pk/Samsung_Galaxy-S24-Plus"},
            {"url": "https://www.whatmobile.com.pk/Samsung_Galaxy-S24-Ultra"},
        ]
        # A source URL isn't evidence of the model; the parsed title must match.
        result = research_urls(criteria, urls, provider="tavily")
        self.assertEqual(result["status"], "grounded_preview")
        self.assertEqual(result["document"]["phones"][0]["name"], "Galaxy S24 Ultra")
        self.assertEqual(result["document"]["phones"][0]["ram_gb"], 12)

    def test_coming_soon_navigation_does_not_reject_a_real_price(self):
        from .source_research import parse_product
        html = S24_HTML.replace("<div>Rs. 434,999</div>",
                                "<nav>Coming Soon</nav><div>Rs. 434,999</div>")
        found = parse_product(html, "https://www.whatmobile.com.pk/Samsung_Galaxy-S24-Ultra", "Samsung")
        self.assertEqual(found["price_min_pkr"], "434999")
        expected = S24_HTML.replace("Rs. 434,999", "Rs. Coming Soon (Expected Rs. 434,999)")
        with self.assertRaises(ValueError):
            parse_product(expected, "https://www.whatmobile.com.pk/Samsung_Galaxy-S24-Ultra", "Samsung")

    @patch("recommendations.source_research._fetch", return_value=S24_HTML)
    def test_tavily_zero_hits_can_still_find_exact_product(self, fetch):
        criteria = {"brand": "samsung", "device_query": "Galaxy S24 Ultra"}
        from .source_research import research_source_pages
        found = research_source_pages(criteria)
        self.assertEqual(found["status"], "grounded_preview")
        self.assertEqual(found["document"]["phones"][0]["storage_gb"], 256)

    @override_settings(WEB_RESEARCH_ENABLED=True, WEB_SEARCH_PROVIDER="tavily")
    @patch("recommendations.research_providers.research_source_pages")
    @patch("recommendations.research_providers.research_with_tavily")
    def test_unpriced_tavily_result_tries_direct_price_page(self, tavily, direct):
        from .research_providers import research_catalog
        tavily.return_value = {"status": "specifications_only", "sources": []}
        direct.return_value = {"status": "grounded_preview", "document": {"phones": []}, "sources": []}
        with patch("recommendations.research_providers.search_selection", return_value="tavily"):
            result = research_catalog({"device_query": "Galaxy S24 Ultra"})
        self.assertEqual(result["status"], "grounded_preview")
        direct.assert_called_once()

    @patch("recommendations.views.GeminiResearchThrottle.allow_request", return_value=True)
    @patch("recommendations.views.research_configured", return_value=True)
    @patch("recommendations.views.research_and_save")
    @patch("recommendations.views.Device.objects.filter")
    def test_comparison_returns_imported_exact_device(self, device_filter, research, configured, throttle):
        # Initial catalog lookup empty; post-import query finds the saved phone.
        device = Mock(slug="samsung-galaxy-s24-ultra", name="Galaxy S24 Ultra")
        device.name = "Galaxy S24 Ultra"
        device.brand.name = "Samsung"
        device.primary_image_url = ""
        device.data_source = "web_research"
        local = MagicMock()
        local.select_related.return_value = local
        local.filter.return_value = local
        local.__getitem__.return_value = []
        imported = Mock()
        imported.select_related.return_value = [device]
        device_filter.side_effect = [local, imported]
        research.return_value = {"status": "grounded_preview", "results": [],
                                 "saved_device_slugs": [device.slug],
                                 "saved": {"devices_created": 1, "prices_saved": 1}, "sources": []}
        request = APIRequestFactory().post(
            "/api/recommendations/compare-lookup/", {"query": "samsung s24 ultra"}, format="json"
        )
        view = ComparisonPhoneLookupView.as_view()
        # Disable APIView's per-request throttle for this isolated view test.
        with patch.object(ComparisonPhoneLookupView, "throttle_classes", []):
            response = view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["devices"][0]["slug"], device.slug)
        self.assertEqual(response.data["status"], "researched")
