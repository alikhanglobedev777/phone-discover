"""Pakistani retailer discovery with exact-model and price evidence guards."""

import json
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from .catalog_research import source_url
from .source_research import parse_pakistan_retailer_product, research_urls, _fetch


SHOPHIVE_HTML = """
<header><p>Featured model Rs. 19,999</p></header>
<h1>Samsung Galaxy S26 Ultra 12GB 256GB</h1>
<div class="product">In stock</div>
<div class="price">Special Price Rs 384,999.00 was Rs 449,999.00</div>
<button>Add to Cart</button>
"""
SELECTO_HTML = """
<h1>Samsung Galaxy S26 Ultra 12+256GB with Samsung Buds Core</h1>
<p>In Stock</p><div>Rs.386,500 Rs.444,999</div><button>Buy Now</button>
"""
CRITERIA = {"brand": "samsung", "device_query": "Galaxy S26 Ultra",
            "comparison_target": "samsung s26 ultra"}


class PakistaniRetailerSearchTests(SimpleTestCase):
    def test_search_accepts_pakistani_hosts_not_only_old_two(self):
        self.assertEqual(source_url("https://www.shophive.com/samsung-galaxy-s26-ultra-12gb-256gb/?ref=abc"),
                         "https://www.shophive.com/samsung-galaxy-s26-ultra-12gb-256gb")
        self.assertEqual(source_url("https://www.selecto.com.pk/products/samsung-s26-ultra"),
                         "https://www.selecto.com.pk/products/samsung-s26-ultra")
        self.assertIsNone(source_url("http://www.shophive.com/phone"))
        self.assertIsNone(source_url("https://shophive.com.attacker.example/phone"))
        self.assertIsNone(source_url("https://127.0.0.1/phone"))
        self.assertIsNone(source_url("https://example.org/phone"))

    def test_shophive_variant_and_actual_discounted_price(self):
        result = parse_pakistan_retailer_product(
            SHOPHIVE_HTML, "https://www.shophive.com/samsung-galaxy-s26-ultra-12gb-256gb/", CRITERIA)
        self.assertEqual((result["brand"], result["name"]), ("Samsung", "Galaxy S26 Ultra"))
        self.assertEqual((result["ram_gb"], result["storage_gb"]), (12, 256))
        self.assertEqual(result["price_min_pkr"], "384999")
        self.assertEqual(result["pta_status"], "unknown")

    def test_general_pk_seller_with_bundle(self):
        result = parse_pakistan_retailer_product(
            SELECTO_HTML, "https://selecto.com.pk/products/samsung-galaxy-s26-ultra", CRITERIA)
        self.assertEqual(result["name"], "Galaxy S26 Ultra")
        self.assertEqual(result["price_min_pkr"], "386500")

    def test_sibling_model_is_rejected(self):
        html = SHOPHIVE_HTML.replace("S26 Ultra", "S26 Plus")
        with self.assertRaises(ValueError):
            parse_pakistan_retailer_product(html, "https://shophive.com/other", CRITERIA)

    def test_no_ambiguous_variant_import(self):
        html = SHOPHIVE_HTML.replace("12GB 256GB", "12GB 256GB / 12GB 512GB")
        with self.assertRaises(ValueError):
            parse_pakistan_retailer_product(html, "https://shophive.com/other", CRITERIA)

    def test_estimated_price_is_not_imported(self):
        html = SHOPHIVE_HTML.replace("Special Price Rs 384,999.00", "Expected Price Rs 384,999.00")
        with self.assertRaises(ValueError):
            parse_pakistan_retailer_product(html, "https://shophive.com/other", CRITERIA)

    def test_price_must_be_pkr_and_on_product_page(self):
        html = SHOPHIVE_HTML.replace("Special Price Rs 384,999.00", "Special Price $ 1299")
        with self.assertRaises(ValueError):
            parse_pakistan_retailer_product(html, "https://shophive.com/other", CRITERIA)

    @patch("recommendations.source_research._fetch", return_value=SHOPHIVE_HTML)
    def test_tavily_search_results_can_be_saved_from_shophive(self, fetch):
        url = "https://www.shophive.com/samsung-galaxy-s26-ultra-12gb-256gb/"
        result = research_urls(CRITERIA, [{"url": url}], provider="tavily")
        self.assertEqual(result["status"], "grounded_preview")
        self.assertEqual(result["document"]["phones"][0]["price_min_pkr"], "384999")
        self.assertEqual(result["sources"][0]["url"], url.rstrip("/"))

    @patch("recommendations.source_research.socket.getaddrinfo")
    def test_private_dns_is_never_fetched(self, resolve):
        resolve.return_value = [(0, 0, 0, "", ("10.0.0.10", 443))]
        with self.assertRaises(ValueError):
            _fetch("https://example.pk/product/samsung")

    @override_settings(WEB_SEARCH_PROVIDER="tavily")
    @patch("recommendations.research_providers.research_urls")
    @patch("recommendations.research_providers.build_opener")
    @patch("recommendations.research_providers.key_for", return_value="test-key")
    def test_tavily_does_not_restrict_search_to_two_domains(self, _key, opener, urls):
        from .research_providers import research_with_tavily
        response = Mock()
        response.read.return_value = b'{"results": []}'
        opener.return_value.open.return_value.__enter__ = Mock(return_value=response)
        opener.return_value.open.return_value.__exit__ = Mock(return_value=False)
        urls.return_value = {"status": "no_sources", "sources": []}
        research_with_tavily(CRITERIA)
        body = json.loads(opener.return_value.open.call_args.args[0].data)
        self.assertNotIn("include_domains", body)
        self.assertIn("Galaxy S26 Ultra", body["query"])
        self.assertNotIn('"samsung s26 ultra"', body["query"])
