from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Brand, Device, DeviceVariant, MarketPriceObservation, ResearchSource
from catalog.search import search_local_catalog
from catalog.web_import import import_web_phones
from .automatic_research import research_and_save
from .catalog_research import catalog_prompt, source_url
from .local_intent import parse_pakistan_intent
from .source_research import parse_product


URL = "https://www.whatmobile.com.pk/Samsung_Galaxy-A57"
PHONE = {"brand": "Samsung", "name": "Galaxy A57", "ram_gb": 8, "storage_gb": 256,
         "source_url": URL, "price_min_pkr": "166999", "price_max_pkr": "166999", "condition": "box_pack",
         "pta_status": "unknown", "city": "", "listing_status": "unknown", "image_url": "",
         "chipset": "Exynos 1680", "specifications": {"Main camera": "50 MP with OIS"}}


def preview():
    return {"status": "grounded_preview", "document": {"phones": [deepcopy(PHONE)]},
            "sources": [{"url": URL, "title": "Samsung Galaxy A57"}], "notice": "Source-reported facts"}


@override_settings(GEMINI_AUTO_RESEARCH_ENABLED=True, GEMINI_WEB_RESEARCH_ENABLED=True,
                   GEMINI_API_KEY="test-only", GEMINI_CHAT_MODEL="test-model",
                   GEMINI_RESEARCH_SOURCE_DOMAINS=("whatmobile.com.pk", "priceoye.pk"))
class AutomaticResearchTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        for target in ("PakistanConversationView.throttle_classes",):
            mock = patch("recommendations.views." + target, [])
            mock.start()
            self.addCleanup(mock.stop)
        mock = patch("recommendations.views.GeminiResearchThrottle.allow_request", return_value=True)
        mock.start()
        self.addCleanup(mock.stop)

    def ask(self, **fields):
        response = self.client.post("/api/recommendations/converse/", {
            "message": "Samsung Galaxy A57 under PKR 200000", "use_memory": False, **fields,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_no_local_match_researches_saves_and_returns_cards_then_reuses_database(self):
        with patch("recommendations.automatic_research.research_catalog", return_value=preview()) as remote:
            response = self.ask()
            self.assertTrue(response["research_automatic"])
            self.assertTrue(response["catalog_updated"])
            self.assertEqual(response["research"]["saved"]["devices_created"], 1)
            self.assertEqual(response["results"][0]["device"]["slug"], "samsung-galaxy-a57")
            again = self.ask()
        remote.assert_called_once()
        self.assertFalse(again["research_automatic"])
        self.assertEqual(Device.objects.count(), 1)
        self.assertEqual(MarketPriceObservation.objects.count(), 1)
        price = MarketPriceObservation.objects.get()
        self.assertEqual(price.verification_status, "web_reported")
        self.assertIsNone(price.reviewed_at)
        self.assertEqual(price.pta_verification, "unknown")
        self.assertEqual(response["results"][0]["market_price"]["evidence_type"], "web_researched")
        catalog = self.client.get("/api/catalog/devices/").data["results"][0]
        self.assertEqual(catalog["data_source"], "web_research")
        self.assertEqual(catalog["lowest_price"]["currency"], "PKR")

    def test_unknown_city_is_preserved_and_web_cards_are_separate(self):
        with patch("recommendations.automatic_research.research_catalog", return_value=preview()):
            result = self.ask(city="Karachi", pta_status="approved")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["results"], [])
        self.assertEqual(len(result["research"]["results"]), 1)
        price = MarketPriceObservation.objects.get()
        self.assertEqual(price.city, "")
        self.assertEqual(price.pta_status, "unknown")

    def test_reimport_deduplicates_and_preserves_catalog_edits(self):
        import_web_phones(preview())
        device = Device.objects.get()
        device.summary = "Reviewed admin description"
        device.primary_image_url = "https://example.org/custom.jpg"
        device.save()
        import_web_phones(preview())
        device.refresh_from_db()
        self.assertEqual(Device.objects.count(), 1)
        self.assertEqual(DeviceVariant.objects.count(), 1)
        self.assertEqual(MarketPriceObservation.objects.count(), 1)
        self.assertEqual(device.summary, "Reviewed admin description")
        self.assertEqual(device.primary_image_url, "https://example.org/custom.jpg")

    def test_invalid_and_uncited_records_cannot_create_partial_catalog_data(self):
        for change in ({"source_url": "https://www.whatmobile.com.pk/uncited"}, {"price_min_pkr": "NaN"},
                       {"price_max_pkr": "1"}, {"ram_gb": True}, {"pta_status": "checked"}):
            research = preview()
            research["document"]["phones"][0].update(change)
            stats, slugs = import_web_phones(research)
            self.assertEqual(stats["rejected"], 1)
            self.assertEqual(slugs, [])
        self.assertEqual(Device.objects.count(), 0)
        self.assertEqual(ResearchSource.objects.count(), 0)

    def test_restricted_source_and_unpublished_phone_stay_blocked(self):
        source = ResearchSource.objects.create(url=URL, title="Restricted", reuse_status="restricted")
        self.assertEqual(import_web_phones(preview())[0]["rejected"], 1)
        self.assertFalse(Device.objects.exists())
        source.reuse_status, source.reuse_notes = "permitted", "Test basis"
        source.save()
        brand = Brand.objects.create(name="Samsung", slug="samsung")
        Device.objects.create(brand=brand, name="Galaxy A57", slug="samsung-galaxy-a57", is_published=False)
        self.assertEqual(import_web_phones(preview())[0]["rejected"], 1)
        self.assertFalse(MarketPriceObservation.objects.exists())

    def test_cached_research_does_not_refresh_observation_timestamp(self):
        criteria = {"message": "A57", "session_id": "test", "budget_pkr": 200000,
                    "priorities": [], "strict_budget": True, "max_results": 3, "response_language": "english"}
        with patch("recommendations.automatic_research.research_catalog", return_value=preview()) as remote:
            research_and_save(criteria)
            observed = MarketPriceObservation.objects.get().observed_at
            result = research_and_save(criteria)
        self.assertTrue(result["cached"])
        remote.assert_called_once()
        self.assertEqual(MarketPriceObservation.objects.get().observed_at, observed)

    def test_google_quota_failure_uses_source_page_fallback(self):
        with patch("recommendations.research_providers.research_catalog_with_gemini", return_value={"status": "quota_exceeded"}), \
             patch("recommendations.research_providers.research_source_pages", return_value=preview()) as source:
            response = self.ask()
        source.assert_called_once()
        self.assertEqual(response["research"]["provider_status"], "quota_exceeded")
        self.assertTrue(response["catalog_updated"])

    def test_stale_and_rejected_web_prices_do_not_appear(self):
        import_web_phones(preview())
        price = MarketPriceObservation.objects.get()
        price.observed_at = timezone.now() - timedelta(days=31)
        price.save()
        self.assertEqual(search_local_catalog({})["count"], 0)
        price.observed_at, price.verification_status = timezone.now(), "rejected"
        price.save()
        self.assertEqual(search_local_catalog({})["count"], 0)
        self.assertEqual(import_web_phones(preview())[0]["rejected"], 1)

    def test_cached_cards_respect_source_revocation(self):
        criteria = {"message": "A57", "session_id": "test", "priorities": [],
                    "strict_budget": True, "max_results": 3, "response_language": "english"}
        with patch("recommendations.automatic_research.research_catalog", return_value=preview()):
            research_and_save(criteria)
        ResearchSource.objects.update(reuse_status="restricted")
        cached = research_and_save(criteria)
        self.assertTrue(cached["cached"])
        self.assertEqual(cached["results"], [])


class SourceResearchParsingTests(SimpleTestCase):
    def test_actual_product_markup_extracts_facts_without_inventing_city_or_pta(self):
        html = '''<h1>Samsung Galaxy A57</h1><span>Rs. 166,999</span>
        <img class="product-image" src="admin/images/Samsung/SamsungGalaxyA57-b.jpg">
        <th class="specs-subHeading">Built-in</th><td class="specs-value">256GB Built-in, 8GB RAM</td>
        <th class="specs-subHeading">Chipset</th><td class="specs-value">Exynos 1680</td>'''
        phone = parse_product(html, URL, "Samsung")
        self.assertEqual(phone["price_min_pkr"], "166999")
        self.assertEqual(phone["storage_gb"], 256)
        self.assertEqual(phone["ram_gb"], 8)
        self.assertEqual(phone["city"], "")
        self.assertEqual(phone["pta_status"], "unknown")
        with self.assertRaises(ValueError):
            parse_product(html.replace("256GB Built-in", "128/256GB Built-in"), URL, "Samsung")

    def test_model_queries_are_exact_and_prompt_contains_no_private_chat(self):
        self.assertEqual(parse_pakistan_intent("Samsung Galaxy A57 under 200k")["device_query"], "Galaxy A57")
        self.assertEqual(parse_pakistan_intent("Vivo V60 Lite")["device_query"], "V60 Lite")
        self.assertNotIn("PRIVATE", catalog_prompt({"message": "PRIVATE", "session_id": "PRIVATE", "city": "Karachi"}))
        for bad in ("https://127.0.0.1/x", "https://localhost/x", "https://whatmobile.com.pk.evil.test/x", "https://www.whatmobile.com.pk:bad/x"):
            self.assertIsNone(source_url(bad))
