"""Do not replace specific phone models with other phones of the same brand."""

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .local_intent import parse_pakistan_intent
from .local_rank import rank_pakistan_phones
from .model_identity import matches_phone_model
from .automatic_research import research_and_save


class ExactModelChatTests(SimpleTestCase):
    def test_vivo_x90s_intent_is_exact(self):
        parsed = parse_pakistan_intent("Tell me about Vivo X90s in Pakistan")
        self.assertEqual(parsed["brand"], "vivo")
        self.assertEqual(parsed["device_query"].casefold(), "x90s")

    def test_sibling_models_are_not_equivalent(self):
        self.assertTrue(matches_phone_model("vivo x90s", "Vivo", "X90s"))
        self.assertTrue(matches_phone_model("Vivo X90s 8GB 256GB Pakistan", "Vivo", "X90s"))
        self.assertFalse(matches_phone_model("vivo x90s", "Vivo", "V80 Lite"))
        self.assertFalse(matches_phone_model("vivo x90s", "Vivo", "X90s Pro"))
        self.assertFalse(matches_phone_model("Samsung Galaxy A57", "Samsung", "Galaxy A57 Pro"))
        self.assertTrue(matches_phone_model("Nothing Phone 2", "Nothing", "Phone 2"))

    @patch("recommendations.local_rank.search_local_catalog")
    def test_rank_rejects_other_vivo_phone_even_when_catalog_returns_it(self, search):
        search.return_value = {"count": 1, "has_more": False, "results": [
            {"name": "V80 Lite", "brand": {"name": "Vivo"}}
        ]}
        criteria = {"device_query": "X90s", "priorities": [], "strict_budget": True,
                    "max_results": 3, "budget_pkr": None}
        result = rank_pakistan_phones(criteria)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["results"], [])
        self.assertTrue(result["needs_research"])

    @override_settings(WEB_SEARCH_PROVIDER="source_pages", API_KEY="")
    @patch("recommendations.automatic_research._cache_key", return_value="test-exact-model")
    @patch("recommendations.automatic_research.cached_research", return_value=None)
    @patch("recommendations.automatic_research.cache")
    @patch("recommendations.automatic_research.import_web_phones")
    @patch("recommendations.automatic_research.research_catalog")
    def test_unrelated_web_phone_cannot_enter_database(self, research, importer, cache,
                                                         _cached, _key):
        cache.add.return_value = True
        research.return_value = {
            "status": "grounded_preview", "provider": "tavily", "results": [],
            "document": {"phones": [
                {"brand": "Vivo", "name": "V80 Lite", "source_url": "https://www.whatmobile.com.pk/Vivo_V80-Lite"}
            ]},
            "sources": [{"url": "https://www.whatmobile.com.pk/Vivo_V80-Lite"}],
        }
        importer.return_value = ({"devices_created": 0, "prices_saved": 0, "rejected": 0}, [])
        result = research_and_save({"device_query": "X90s", "brand": "vivo"})
        imported = importer.call_args.args[0]
        self.assertEqual(imported["document"]["phones"], [])
        self.assertEqual(imported["sources"], [])
        self.assertEqual(result["status"], "no_sources")
        self.assertEqual(result["results"], [])

    @override_settings(WEB_SEARCH_PROVIDER="source_pages", API_KEY="")
    @patch("recommendations.automatic_research._cache_key", return_value="test-exact-model")
    @patch("recommendations.automatic_research.cached_research", return_value=None)
    @patch("recommendations.automatic_research.cache")
    @patch("recommendations.automatic_research.import_web_phones")
    @patch("recommendations.automatic_research.research_catalog")
    def test_only_exact_model_is_passed_to_importer(self, research, importer, cache,
                                                      _cached, _key):
        cache.add.return_value = True
        research.return_value = {
            "status": "grounded_preview", "provider": "tavily", "results": [],
            "document": {"phones": [
                {"brand": "Vivo", "name": "V80 Lite", "source_url": "https://www.whatmobile.com.pk/Vivo_V80-Lite"},
                {"brand": "Vivo", "name": "X90s", "source_url": "https://www.whatmobile.com.pk/Vivo_X90s"},
            ]},
            "sources": [
                {"url": "https://www.whatmobile.com.pk/Vivo_V80-Lite"},
                {"url": "https://www.whatmobile.com.pk/Vivo_X90s"},
            ],
        }
        importer.return_value = ({"devices_created": 0, "prices_saved": 0, "rejected": 0}, [])
        research_and_save({"device_query": "X90s", "brand": "vivo"})
        imported = importer.call_args.args[0]
        self.assertEqual([p["name"] for p in imported["document"]["phones"]], ["X90s"])
        self.assertEqual([s["url"] for s in imported["sources"]], ["https://www.whatmobile.com.pk/Vivo_X90s"])
