"""Stage 3: referential follow-ups must not invent eligibility or a comparison pair."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import (
    Brand, Device, DeviceVariant, MarketPriceObservation, ResearchSource,
    ReviewStatus,
)
from recommendations.conversation import previous_context


@override_settings(GEMINI_AUTO_RESEARCH_ENABLED=False, GEMINI_WEB_RESEARCH_ENABLED=False)
class NaturalFollowupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        samsung = Brand.objects.create(name="Samsung", slug="samsung")
        google = Brand.objects.create(name="Google", slug="google")
        cls.source = ResearchSource.objects.create(
            url="https://example.org/test-permitted", title="Approved test",
            reuse_status=ResearchSource.ReuseStatus.PERMITTED,
            reuse_notes="Fictitious test fixture",
        )
        cls.ultra = Device.objects.create(
            brand=samsung, name="Galaxy S26 Ultra", slug="s26-ultra", is_published=True,
        )
        cls.base = Device.objects.create(
            brand=samsung, name="Galaxy S26", slug="s26", is_published=True,
        )
        cls.pixel = Device.objects.create(
            brand=google, name="Pixel 7a", slug="pixel-7a", is_published=True,
        )
        cls.ultra_variant = DeviceVariant.objects.create(
            device=cls.ultra, name="12/256", ram_gb=12, storage_gb=256,
            camera_score=95, battery_score=88,
        )
        cls.base_variant = DeviceVariant.objects.create(
            device=cls.base, name="8/128", ram_gb=8, storage_gb=128,
            camera_score=75, battery_score=72,
        )
        cls.pixel_variant = DeviceVariant.objects.create(
            device=cls.pixel, name="8/128", ram_gb=8, storage_gb=128,
            camera_score=89, battery_score=0,
        )

    def setUp(self):
        self.client = APIClient()
        throttle = patch("recommendations.views.PakistanConversationView.throttle_classes", [])
        throttle.start()
        self.addCleanup(throttle.stop)

    def ask(self, message, **kwargs):
        return self.client.post("/api/recommendations/converse/",
                                {"message": message, **kwargs}, format="json")

    def add_price(self, variant, status):
        return MarketPriceObservation.objects.create(
            source=self.source, variant=variant, city="Lahore",
            condition="used", grade="good", pta_status=status,
            pta_verification="reported",
            price_min_pkr=Decimal("65000"), price_max_pkr=Decimal("69000"),
            observed_at=timezone.now() - timedelta(hours=1),
            reviewed_at=timezone.now() - timedelta(minutes=5),
            verification_status=ReviewStatus.VERIFIED, listing_status="active",
        )

    def test_pta_only_filters_previous_shortlist_and_does_not_show_unpriced_results(self):
        first = self.ask("Best camera phone", max_results=3)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(len(first.data["specs_results"]), 3)
        self.assertEqual(first.data["results"], [])
        self.assertEqual(len(previous_context(first.data["session_id"])["recent_device_slugs"]), 3)
        self.add_price(self.base_variant, "approved")
        self.add_price(self.ultra_variant, "non_pta")
        filtered = self.ask("Show only PTA approved options", session_id=first.data["session_id"])
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.data["criteria"]["pta_status"], "approved")
        self.assertEqual(filtered.data["results"][0]["device"]["slug"], "s26")
        self.assertEqual([p["device"]["slug"] for p in filtered.data["results"]], ["s26"])
        self.assertEqual(filtered.data["specs_results"], [])
        self.assertEqual(filtered.data["catalog_details"], [])
        self.assertIn("previously discussed", filtered.data["explanation"])
        self.assertEqual(len(previous_context(first.data["session_id"])["recent_device_slugs"]), 3)

    def test_unpriced_pta_only_followup_reports_no_verified_eligible_options(self):
        first = self.ask("Best camera phone")
        filtered = self.ask("sirf PTA approved phones", session_id=first.data["session_id"])
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.data["results"], [])
        self.assertEqual(filtered.data["specs_results"], [])
        self.assertEqual(filtered.data["price_references"]["results"], [])
        self.assertIn("won't treat saved specifications as proof", filtered.data["explanation"])

    def test_ambiguous_which_is_better_after_three_options_asks_to_name_two(self):
        first = self.ask("best camera phones", max_results=3)
        response = self.ask("Which one has better battery?", session_id=first.data["session_id"])
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["comparison"])
        self.assertEqual(response.data["results"], [])
        self.assertEqual(response.data["catalog_details"], [])
        self.assertIn("name the two phones", response.data["explanation"])
        self.assertEqual(response.data["research"]["status"], "not_requested")

    def test_compare_new_phone_to_single_previous_and_followup_battery(self):
        first = self.ask("Galaxy S26 Ultra")
        self.assertEqual(first.status_code, 200)
        second = self.ask("Compare it with Pixel 7a", session_id=first.data["session_id"])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            [p["slug"] for p in second.data["comparison"]["phones"]],
            ["s26-ultra", "pixel-7a"],
        )
        self.assertIsNone(second.data["criteria"].get("device_query"))
        self.assertIsNone(second.data["criteria"].get("brand"))
        third = self.ask("Which one has better battery?", session_id=first.data["session_id"])
        self.assertEqual(third.status_code, 200)
        battery = next(row for row in third.data["comparison"]["dimensions"]
                       if row["dimension"] == "battery")
        self.assertIsNone(battery["leader_slug"])
        self.assertIn("Insufficient", battery["note"])

    def test_no_memory_comparison_does_not_infer_unrelated_prior_phone(self):
        first = self.ask("Galaxy S26 Ultra")
        result = self.ask("Compare it with Pixel 7a", session_id=first.data["session_id"],
                          use_memory=False)
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.data["comparison"])
        self.assertIn("name the two phones", result.data["explanation"])

    def test_plain_brand_followup_releases_prior_exact_model(self):
        first = self.ask("Samsung Galaxy S26 Ultra")
        second = self.ask("Show Samsung phones", session_id=first.data["session_id"])
        self.assertEqual(second.status_code, 200)
        self.assertIsNone(second.data["criteria"].get("device_query"))
        self.assertEqual(second.data["criteria"]["brand"], "samsung")
