"""Groq web research tests. All HTTP, Groq and retailer-page traffic is mocked."""

import json
from unittest.mock import patch
from urllib.error import HTTPError

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from catalog.models import Device, MarketPriceObservation
from .automatic_research import research_and_save
from .provider_config import ai_selection, key_for, public_provider_status, search_selection
from .research_providers import _groq_search_urls, research_catalog, research_with_groq


SOURCE = "https://www.whatmobile.com.pk/Samsung_Galaxy-A57"
EXTERNAL = "https://evil.example/Samsung_Galaxy-A57"
HTML = ("""<h1>Samsung Galaxy A57</h1><span>Rs. 166,999</span>
<th class="specs-subHeading">Built-in</th><td class="specs-value">256GB Built-in, 8GB RAM</td>
<th class="specs-subHeading">Chipset</th><td class="specs-value">Exynos 1680</td>""")
BASE = dict(API_KEY="", API_PROVIDER="auto", AI_PROVIDER="groq", AI_MODEL="",
            GROQ_API_KEY="gsk_fake-not-real", GROQ_MODEL="openai/gpt-oss-20b",
            GROQ_WEB_MODEL="openai/gpt-oss-20b", GEMINI_API_KEY="", OPENAI_API_KEY="",
            TAVILY_API_KEY="", WEB_SEARCH_PROVIDER="groq", WEB_RESEARCH_ENABLED=True,
            AUTO_WEB_RESEARCH_ENABLED=True, GEMINI_WEB_RESEARCH_ENABLED=True,
            GEMINI_AUTO_RESEARCH_ENABLED=True, GEMINI_RESEARCH_TIMEOUT_SECONDS=8,
            GEMINI_RESEARCH_SOURCE_DOMAINS=("whatmobile.com.pk", "priceoye.pk"))


def groq_payload(url=SOURCE, *, include_tool=True, finish="stop"):
    return {"choices": [{"finish_reason": finish, "message": {
        "content": "Here is a price: PKR 123",  # NEVER copied to the catalog
        "executed_tools": ([{"type": "browser_search", "search_results": {
            "results": [{"url": url, "title": "Search result"}]}}] if include_tool else [])
    }}]}


class HttpResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, size):
        return self.body[:size]


@override_settings(**BASE)
class GroqWebResearchTests(SimpleTestCase):
    def test_selected_provider_is_groq_and_keys_stay_private(self):
        self.assertEqual(ai_selection(), "groq")
        self.assertEqual(search_selection(), "groq")
        self.assertTrue(public_provider_status()["automatic_research"])
        self.assertNotIn("gsk_fake-not-real", str(public_provider_status()))
        self.assertEqual(key_for("groq"), "gsk_fake-not-real")
        self.assertEqual(key_for("gemini"), "")
        with override_settings(WEB_SEARCH_PROVIDER="auto"):
            self.assertEqual(search_selection(), "groq")
        with override_settings(WEB_SEARCH_PROVIDER="gemini"):
            self.assertEqual(search_selection(), "unavailable")

    def test_only_tool_returned_approved_urls_are_eligible(self):
        self.assertEqual(_groq_search_urls(groq_payload(EXTERNAL)), [])
        self.assertEqual(_groq_search_urls(groq_payload(SOURCE, include_tool=False)), [])
        self.assertEqual(_groq_search_urls(groq_payload(SOURCE, finish="length")), [])
        self.assertEqual(_groq_search_urls({"choices": [{"finish_reason": "stop", "message": {
            "content": f"Found {SOURCE}"}}]}), [])
        self.assertEqual(_groq_search_urls(groq_payload())[0]["url"], SOURCE)
        fake = groq_payload()
        fake["choices"][0]["message"]["executed_tools"] = [
            {"type": "code_interpreter", "search_results": {"results": [{"url": SOURCE}]}},
            {"type": "browser_search", "search_results": {"results": [{"url": SOURCE}, {"url": SOURCE}]}},
        ]
        self.assertEqual(len(_groq_search_urls(fake)), 1)

    @patch("recommendations.research_providers.build_opener")
    @patch("recommendations.research_providers.research_urls")
    def test_groq_search_requires_browser_tool_and_visits_only_allowed_sources(self, page_reader, opener):
        opener.return_value.open.return_value = HttpResponse(groq_payload())
        page_reader.return_value = {"status": "grounded_preview", "provider": "groq", "document": {"phones": []}, "sources": []}
        result = research_with_groq({"device_query": "Galaxy A57", "budget_pkr": 200000})
        self.assertEqual(result["provider"], "groq")
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.groq.com/openai/v1/chat/completions")
        body = json.loads(request.data)
        self.assertEqual(body["tools"], [{"type": "browser_search"}])
        self.assertEqual(body["tool_choice"], "required")
        self.assertEqual(body["model"], "openai/gpt-oss-20b")
        self.assertNotIn("gsk_fake-not-real", json.dumps(body))
        self.assertIn("Bearer gsk_fake-not-real", request.headers["Authorization"])
        self.assertEqual(page_reader.call_args.args[1][0]["url"], SOURCE)

    @patch("recommendations.research_providers.build_opener")
    @patch("recommendations.research_providers.research_urls")
    def test_untrusted_text_without_tool_sources_never_reaches_page_reader(self, page_reader, opener):
        opener.return_value.open.return_value = HttpResponse(groq_payload(EXTERNAL))
        result = research_with_groq({"device_query": "A57"})
        self.assertEqual(result["status"], "no_sources")
        page_reader.assert_not_called()
        with override_settings(GROQ_WEB_MODEL="groq/compound"):
            result = research_with_groq({"device_query": "A57"})
            self.assertEqual(result["status"], "unsupported_model")
            self.assertEqual(opener.return_value.open.call_count, 1)

    @patch("recommendations.research_providers.build_opener")
    def test_production_http_401_and_403_have_distinct_safe_statuses(self, opener):
        for code, expected in ((401, "authentication_failed"), (403, "access_denied")):
            with self.subTest(code=code):
                opener.return_value.open.side_effect = HTTPError(
                    "https://api.groq.com", code, "private-response-must-not-leak", {}, None)
                with patch("recommendations.research_providers.research_source_pages", return_value={
                    "status": "no_sources", "provider": "source_pages", "document": {"phones": []},
                    "sources": [], "notice": "No page evidence"}):
                    result = research_catalog({"device_query": "A57"})
                self.assertEqual(result["status"], expected)
                self.assertNotIn("gsk_fake-not-real", str(result))
                self.assertNotIn("private-response-must-not-leak", str(result))
                if code == 403:
                    self.assertIn("model", result["notice"])

    @patch("recommendations.research_providers.build_opener")
    def test_rate_limit_fails_closed(self, opener):
        opener.return_value.open.side_effect = HTTPError(
            "https://api.groq.com", 429, "quota", {}, None)
        with patch("recommendations.research_providers.research_source_pages", return_value={
            "status": "no_sources", "provider": "source_pages", "document": {"phones": []}, "sources": [], "notice": "No source found"
        }):
            result = research_catalog({"device_query": "A57"})
        self.assertEqual(result["status"], "quota_exceeded")


@override_settings(**BASE)
class GroqSavingTests(TestCase):
    @patch("recommendations.research_providers.build_opener")
    @patch("recommendations.source_research._fetch", return_value=HTML)
    def test_discovery_parses_actual_website_and_saves_unverified_price(self, fetch, opener):
        cache.clear()
        opener.return_value.open.return_value = HttpResponse(groq_payload())
        criteria = {"device_query": "Galaxy A57", "brand": "Samsung", "priorities": [],
                    "budget_pkr": 200000, "max_results": 3, "strict_budget": True}
        result = research_and_save(criteria)
        self.assertEqual(result["status"], "grounded_preview")
        self.assertEqual(result["provider"], "groq")
        self.assertTrue(result["catalog_updated"])
        self.assertEqual(Device.objects.count(), 1)
        row = MarketPriceObservation.objects.get()
        self.assertEqual(int(row.price_min_pkr), 166999)   # from HTML, not the model's PKR 123
        self.assertEqual(row.verification_status, "web_reported")
        self.assertEqual(row.pta_verification, "unknown")
        self.assertEqual(row.listing_url, SOURCE)
        self.assertEqual(len(result["results"]), 1)
        again = research_and_save(criteria)
        self.assertTrue(again["cached"])
        self.assertFalse(again["catalog_updated"])
        self.assertEqual(Device.objects.count(), 1)
        self.assertEqual(MarketPriceObservation.objects.count(), 1)
        opener.return_value.open.assert_called_once()
