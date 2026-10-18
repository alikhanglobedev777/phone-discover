import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from catalog.models import Device, MarketPriceObservation
from .automatic_research import _cache_key
from .provider_config import key_for, ai_selection, search_selection, public_provider_status, model_for
from .research_providers import research_catalog, research_with_openai, research_with_tavily
from .guidance import generate_general_guidance

URL = "https://www.whatmobile.com.pk/Samsung_Galaxy-A57"
PHONE = {"brand": "Samsung", "name": "Galaxy A57", "ram_gb": 8, "storage_gb": 256,
         "source_url": URL, "price_min_pkr": "166999", "price_max_pkr": "166999", "condition": "box_pack"}
HTML = '''<h1>Samsung Galaxy A57</h1><span>Rs. 166,999</span>
<img class="product-image" src="admin/images/Samsung/SamsungGalaxyA57-b.jpg">
<th class="specs-subHeading">Built-in</th><td class="specs-value">256GB Built-in, 8GB RAM</td>'''

BASE = dict(API_KEY="", API_PROVIDER="auto", AI_PROVIDER="auto", AI_MODEL="", WEB_SEARCH_PROVIDER="auto",
            GEMINI_API_KEY="", OPENAI_API_KEY="", TAVILY_API_KEY="", WEB_RESEARCH_ENABLED=True,
            AUTO_WEB_RESEARCH_ENABLED=True, GEMINI_RESEARCH_SOURCE_DOMAINS=("whatmobile.com.pk", "priceoye.pk"))


class HttpResponse:
    def __init__(self, data):
        self.data = data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return json.dumps(self.data).encode()[:size]


@override_settings(**BASE)
class ProviderConfigurationTests(SimpleTestCase):
    def test_single_key_detects_service_and_does_not_forward_to_other_provider(self):
        for key, expected_ai, expected_search in (("AIza-test", "gemini", "gemini"),
                ("sk-test", "openai", "openai"), ("tvly-test", "deterministic", "tavily")):
            with self.subTest(service=expected_search), override_settings(API_KEY=key, GEMINI_API_KEY="old-google-key", OPENAI_API_KEY="old-openai-key"):
                self.assertEqual(ai_selection(), expected_ai)
                self.assertEqual(search_selection(), expected_search)
                self.assertEqual(key_for(expected_search), key)
                for other in {"gemini", "openai", "tavily"} - {expected_search}:
                    self.assertEqual(key_for(other), "")
                self.assertNotIn(key, json.dumps(public_provider_status()))

    def test_separate_ai_and_search_keys_can_be_combined_or_explicitly_selected(self):
        with override_settings(GEMINI_API_KEY="google", OPENAI_API_KEY="openai", TAVILY_API_KEY="tavily"):
            self.assertEqual(ai_selection(), "gemini")
            self.assertEqual(search_selection(), "tavily")
            with override_settings(AI_PROVIDER="openai", WEB_SEARCH_PROVIDER="gemini"):
                self.assertEqual(ai_selection(), "openai")
                self.assertEqual(search_selection(), "gemini")

    def test_unknown_prefix_needs_explicit_provider(self):
        with override_settings(API_KEY="private-unknown-format"):
            self.assertEqual(search_selection(), "unavailable")
            self.assertTrue(public_provider_status()["configuration_error"])
            with override_settings(API_PROVIDER="tavily"):
                self.assertEqual(search_selection(), "tavily")
                self.assertEqual(key_for("tavily"), "private-unknown-format")

    def test_keyless_source_research_and_model_isolation(self):
        self.assertEqual(search_selection(), "source_pages")
        self.assertEqual(ai_selection(), "deterministic")
        self.assertTrue(public_provider_status()["research_available"])
        with override_settings(AI_PROVIDER="openai", OPENAI_API_KEY="x", GEMINI_API_KEY="y", AI_MODEL="custom-openai"):
            self.assertEqual(model_for("openai"), "custom-openai")
            self.assertNotEqual(model_for("gemini"), "custom-openai")

    def test_cache_is_separate_after_provider_or_key_rotation(self):
        with override_settings(API_KEY="tvly-one"):
            old = _cache_key({"city": "Karachi"})
        with override_settings(API_KEY="tvly-two"):
            self.assertNotEqual(old, _cache_key({"city": "Karachi"}))
        self.assertNotIn("tvly-one", old)

    def test_router_uses_selected_adapter(self):
        for provider in ("gemini", "openai", "tavily", "source_pages"):
            target = {"gemini": "research_catalog_with_gemini", "openai": "research_with_openai",
                      "tavily": "research_with_tavily", "source_pages": "research_source_pages"}[provider]
            with self.subTest(provider=provider), override_settings(WEB_SEARCH_PROVIDER=provider, GEMINI_API_KEY="g", OPENAI_API_KEY="o", TAVILY_API_KEY="t"), \
                 patch("recommendations.research_providers." + target, return_value={"status": "grounded_preview", "sources": []}) as adapter:
                result = research_catalog({})
            adapter.assert_called_once()
            self.assertEqual(result["provider"], provider)


@override_settings(**BASE)
class ProviderAdapterTests(SimpleTestCase):
    @override_settings(API_KEY="tvly-test")
    def test_tavily_uses_basic_search_and_bearer_key_without_private_chat(self):
        calls = []
        class Opener:
            def open(self, request, timeout):
                calls.append(request)
                return HttpResponse({"results": [{"url": URL, "title": "A57"}]})
        with patch("recommendations.research_providers.build_opener", return_value=Opener()), \
             patch("recommendations.research_providers.research_urls", return_value={"status": "grounded_preview"}) as extract:
            research_with_tavily({"brand": "samsung", "message": "PRIVATE", "session_id": "PRIVATE"})
        payload = json.loads(calls[0].data)
        self.assertEqual(calls[0].get_header("Authorization"), "Bearer tvly-test")
        self.assertEqual(payload["search_depth"], "basic")
        self.assertFalse(payload["auto_parameters"])
        self.assertNotIn("PRIVATE", str(payload))
        extract.assert_called_once()

    @override_settings(API_KEY="sk-test")
    def test_openai_search_preserves_citations_and_never_stores_provider_history(self):
        raw = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "annotations": [
            {"type": "url_citation", "url": URL, "title": "A57"}]}]}]}
        response = SimpleNamespace(output_text=json.dumps({"phones": [PHONE]}), model_dump=lambda: raw)
        with patch("recommendations.research_providers.OpenAI") as client:
            client.return_value.responses.create.return_value = response
            result = research_with_openai({"device_query": "Galaxy A57", "message": "PRIVATE"})
        self.assertEqual(result["status"], "grounded_preview")
        self.assertEqual(result["sources"][0]["url"], URL)
        request = client.return_value.responses.create.call_args.kwargs
        self.assertFalse(request["store"])
        self.assertEqual(request["tools"][0]["type"], "web_search")
        self.assertNotIn("PRIVATE", request["input"])
        raw["output"] = []
        with patch("recommendations.research_providers.OpenAI") as client:
            client.return_value.responses.create.return_value = response
            self.assertEqual(research_with_openai({})["status"], "unavailable")

    @override_settings(API_KEY="sk-test")
    def test_openai_general_guidance_uses_the_same_global_key(self):
        with patch("recommendations.guidance.OpenAI") as client:
            client.return_value.responses.create.return_value = SimpleNamespace(status="completed", output_text="Check camera samples. Pakistani pricing and PTA status are unverified.")
            result = generate_general_guidance({"message": "camera phone"})
        self.assertEqual(result["status"], "generated")
        self.assertEqual(client.call_args.kwargs["api_key"], "sk-test")
        self.assertFalse(client.return_value.responses.create.call_args.kwargs["store"])


@override_settings(**{**BASE, "API_KEY": "tvly-test"})
class TavilyOnlyIntegrationTests(TestCase):
    def test_tavily_key_alone_saves_a_phone_and_reuses_it_locally(self):
        cache.clear()
        class Opener:
            def open(self, request, timeout):
                return HttpResponse({"results": [{"url": URL, "title": "A57"}]})
        with patch("recommendations.views.PakistanConversationView.throttle_classes", []), \
             patch("recommendations.views.GeminiResearchThrottle.allow_request", return_value=True), \
             patch("recommendations.research_providers.build_opener", return_value=Opener()) as search, \
             patch("recommendations.source_research._fetch", return_value=HTML), \
             patch("recommendations.research_providers.OpenAI") as ai:
            client = APIClient()
            body = {"message": "Samsung Galaxy A57 under 200k", "use_memory": False}
            first = client.post("/api/recommendations/converse/", body, format="json")
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.data["research"]["provider"], "tavily")
            self.assertTrue(first.data["catalog_updated"])
            self.assertEqual(first.data["results"][0]["device"]["slug"], "samsung-galaxy-a57")
            second = client.post("/api/recommendations/converse/", body, format="json")
            self.assertFalse(second.data["research_automatic"])
        search.assert_called_once()
        ai.assert_not_called()
        self.assertEqual(Device.objects.count(), 1)
        self.assertEqual(MarketPriceObservation.objects.count(), 1)
