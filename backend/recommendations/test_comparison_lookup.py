"""Comparison searches stay local-first, bounded, and source-attributed."""
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, SimpleTestCase, override_settings
from rest_framework.test import APIClient

from catalog.models import Brand, Device, MarketPriceObservation
from .automatic_research import _matches_comparison_target
from .test_automatic_research import preview

URL = "/api/recommendations/compare-lookup/"


class ComparisonTargetTests(SimpleTestCase):
    def test_exact_model_and_optional_variant_are_allowed(self):
        source = {"brand": "Samsung", "name": "Galaxy A57"}
        self.assertTrue(_matches_comparison_target(source, "Samsung Galaxy A57"))
        self.assertTrue(_matches_comparison_target(source, "Samsung Galaxy A57 8GB 256GB"))
        self.assertTrue(_matches_comparison_target({"brand": "Samsung", "name": "Samsung Galaxy A57"}, "Samsung Galaxy A57"))
        self.assertFalse(_matches_comparison_target(source, "Samsung Galaxy A57 Pro"))
        self.assertFalse(_matches_comparison_target(source, "Samsung"))


@override_settings(GEMINI_WEB_RESEARCH_ENABLED=True, WEB_RESEARCH_ENABLED=True,
                   API_KEY="", API_PROVIDER="auto", GROQ_WEB_MODEL="openai/gpt-oss-20b",
                   WEB_SEARCH_PROVIDER="groq", GROQ_API_KEY="fake-test-key",
                   GEMINI_RESEARCH_SOURCE_DOMAINS=("whatmobile.com.pk", "priceoye.pk"))
class ComparisonLookupTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        throttle = patch("recommendations.views.ComparisonPhoneLookupView.throttle_classes", [])
        throttle.start(); self.addCleanup(throttle.stop)
        research_throttle = patch("recommendations.views.GeminiResearchThrottle.allow_request", return_value=True)
        research_throttle.start(); self.addCleanup(research_throttle.stop)

    def test_existing_phone_never_calls_internet(self):
        brand = Brand.objects.create(name="Samsung", slug="samsung")
        Device.objects.create(brand=brand, name="Galaxy A57", slug="samsung-galaxy-a57", is_published=True)
        with patch("recommendations.views.research_and_save") as research:
            response = self.client.post(URL, {"query": "Samsung Galaxy A57"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "found_local")
        research.assert_not_called()

    def test_missing_phone_imports_source_and_returns_saved_device(self):
        with patch("recommendations.automatic_research.research_catalog", return_value=preview()) as research:
            response = self.client.post(URL, {"query": "Samsung Galaxy A57"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "researched")
        self.assertEqual(response.data["devices"][0]["slug"], "samsung-galaxy-a57")
        self.assertEqual(MarketPriceObservation.objects.count(), 1)
        self.assertEqual(MarketPriceObservation.objects.get().verification_status, "web_reported")
        research.assert_called_once()
        again = self.client.post(URL, {"query": "Samsung Galaxy A57"}, format="json")
        self.assertEqual(again.data["status"], "found_local")

    def test_different_phone_from_search_is_not_saved(self):
        with patch("recommendations.automatic_research.research_catalog", return_value=preview()):
            response = self.client.post(URL, {"query": "Samsung Galaxy A57 Pro"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["devices"], [])
        self.assertFalse(Device.objects.exists())

    def test_blank_or_too_short_search_rejected(self):
        self.assertEqual(self.client.post(URL, {"query": "a"}, format="json").status_code, 400)
