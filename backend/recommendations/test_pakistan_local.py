"""Patch 06: guarded natural-language recommendations using only local PKR evidence."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import (
    Brand, Device, DeviceVariant, IngestionCandidate,
    MarketPriceObservation, ResearchSource, ReviewStatus,
)
from .local_intent import parse_pakistan_intent
from .models import RecommendationQuery


@override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="mock-do-not-call")
class PakistanLocalRecommendationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = ResearchSource.objects.create(
            url="https://example.org/allowed-study", title="Approved observations",
            reuse_status=ResearchSource.ReuseStatus.PERMITTED,
            reuse_notes="Author provided authorization for structured price reuse.",
        )
        cls.restricted = ResearchSource.objects.create(
            url="https://example.org/not-permitted", title="Restricted",
            reuse_status=ResearchSource.ReuseStatus.RESTRICTED,
        )
        cls.orion = Brand.objects.create(name="Orion", slug="orion")
        cls.samsung = Brand.objects.create(name="Samsung", slug="samsung")
        cls.a = Device.objects.create(
            brand=cls.orion, name="Play", slug="orion-play", is_published=True,
        )
        cls.b = Device.objects.create(
            brand=cls.samsung, name="Lens", slug="samsung-lens", is_published=True,
        )
        cls.hidden = Device.objects.create(
            brand=cls.orion, name="Secret", slug="orion-secret", is_published=False,
        )
        cls.a_low = DeviceVariant.objects.create(
            device=cls.a, name="6GB/128GB", ram_gb=6, storage_gb=128,
            camera_score=50, gaming_score=70, battery_score=75, display_refresh_hz=90,
        )
        cls.a_high = DeviceVariant.objects.create(
            device=cls.a, name="12GB/256GB", ram_gb=12, storage_gb=256,
            camera_score=66, gaming_score=97, battery_score=85, display_refresh_hz=120,
        )
        cls.b_variant = DeviceVariant.objects.create(
            device=cls.b, name="8GB/256GB", ram_gb=8, storage_gb=256,
            camera_score=96, gaming_score=57, battery_score=78, display_refresh_hz=120,
        )
        cls.secret_variant = DeviceVariant.objects.create(
            device=cls.hidden, name="8GB/128GB", ram_gb=8, storage_gb=128,
        )

    def setUp(self):
        self.client = APIClient()

    def price(self, variant=None, **overrides):
        values = {
            "variant": variant or self.a_high,
            "source": self.source,
            "condition": MarketPriceObservation.Condition.USED,
            "grade": MarketPriceObservation.Grade.GOOD,
            "pta_status": MarketPriceObservation.PTAStatus.APPROVED,
            "pta_verification": MarketPriceObservation.PTAVerification.REPORTED,
            "city": "Lahore",
            "price_min_pkr": Decimal("65000"),
            "price_max_pkr": Decimal("70000"),
            "observed_at": timezone.now() - timedelta(hours=8),
            "reviewed_at": timezone.now() - timedelta(hours=5),
            "verification_status": ReviewStatus.VERIFIED,
            "listing_status": MarketPriceObservation.ListingStatus.ACTIVE,
        }
        values.update(overrides)
        return MarketPriceObservation.objects.create(**values)

    def ask(self, message, **fields):
        return self.client.post("/api/recommendations/local/", {"message": message, **fields}, format="json")

    def test_roman_urdu_parsing_uses_pakistan_budget_and_filters(self):
        parsed = parse_pakistan_intent(
            "Mujhe Lahore mein 80 hazar tak used PTA approved camera aur gaming phone batao"
        )
        self.assertEqual(parsed["budget_pkr"], Decimal("80000"))
        self.assertEqual(parsed["condition"], "used")
        self.assertEqual(parsed["pta_status"], "approved")
        self.assertEqual(parsed["city"], "Lahore")
        self.assertIn("camera", parsed["priorities"])
        self.assertIn("gaming", parsed["priorities"])
        self.assertEqual(parsed["response_language"], "roman_urdu")

    def test_exact_iphone_name_is_preserved_without_inventing_budget(self):
        parsed = parse_pakistan_intent("iPhone 18 Pro Max details")
        self.assertEqual(parsed["brand"], "apple")
        self.assertEqual(parsed["device_query"], "iPhone 18 Pro Max")
        self.assertNotIn("budget_pkr", parsed)
        self.assertNotIn("device_query", parse_pakistan_intent("an Apple phone"))

    def test_explicit_iphone_model_does_not_return_other_iphones(self):
        apple = Brand.objects.create(name="Apple", slug="apple")
        for number in (17, 18):
            name = f"iPhone {number} Pro Max"
            device = Device.objects.create(
                brand=apple, name=name, slug=f"iphone-{number}-pro-max",
                is_published=True,
            )
            variant = DeviceVariant.objects.create(
                device=device, name="256 GB", ram_gb=8, storage_gb=256,
            )
            self.price(variant=variant)
        response = self.ask("iPhone 18 Pro Max")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["device"]["name"] for item in response.data["results"]],
            ["iPhone 18 Pro Max"],
        )

    def test_lakh_and_combined_hazar_amounts(self):
        self.assertEqual(parse_pakistan_intent("1.2 lakh tak")["budget_pkr"], Decimal("120000"))
        self.assertEqual(parse_pakistan_intent("1 lakh 20 hazar budget")["budget_pkr"], Decimal("120000"))
        self.assertEqual(parse_pakistan_intent("under Rs. 90,000")["budget_pkr"], Decimal("90000"))

    def test_hardware_capacity_does_not_become_budget(self):
        parsed = parse_pakistan_intent("12GB RAM 256GB storage under 80k")
        self.assertEqual(parsed["budget_pkr"], Decimal("80000"))
        self.assertEqual(parsed["ram_min"], 12)
        self.assertEqual(parsed["storage_min"], 256)
        self.assertNotIn("budget_pkr", parse_pakistan_intent("12GB RAM 256GB storage"))

    def test_no_prices_returns_research_signal_without_fake_cards(self):
        response = self.ask("Best used gaming phone under 80k")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])
        self.assertTrue(response.data["needs_research"])
        self.assertEqual(response.data["research_reason"], "no_matching_local_evidence")
        self.assertFalse(response.data["research_executed"])

    def test_valid_used_pta_observation_produces_clickable_card(self):
        self.price()
        response = self.ask("Mujhe Lahore mein 80 hazar tak used PTA gaming phone batao")
        self.assertEqual(response.status_code, 200)
        item = response.data["results"][0]
        self.assertEqual(item["device"]["slug"], "orion-play")
        self.assertEqual(item["variant"]["id"], self.a_high.pk)
        self.assertEqual(item["market_price"]["currency"], "PKR")
        self.assertEqual(item["market_price"]["availability"], "not_confirmed")
        self.assertEqual(item["device"]["detail_api_url"], "/api/catalog/devices/orion-play/")
        self.assertFalse(item["fit_score_is_probability"])
        self.assertEqual(response.data["criteria"]["country_code"], "PK")

    def test_strict_budget_uses_upper_bound_and_possible_mode_warns(self):
        self.price(price_min_pkr=Decimal("75000"), price_max_pkr=Decimal("90000"))
        strict = self.ask("Under 80k used phone")
        self.assertEqual(strict.data["results"], [])
        possible = self.ask("Under 80k used phone", strict_budget=False)
        self.assertEqual(possible.status_code, 200)
        self.assertEqual(len(possible.data["results"]), 1)
        self.assertIn("low end", " ".join(possible.data["results"][0]["tradeoffs"]))

    def test_ram_budget_must_match_same_variant(self):
        self.price(variant=self.a_low, price_min_pkr=Decimal("30000"), price_max_pkr=Decimal("35000"))
        self.price(variant=self.a_high, price_min_pkr=Decimal("95000"), price_max_pkr=Decimal("100000"))
        response = self.ask("12gb ram under 50000 used phone")
        self.assertEqual(response.data["results"], [])

    def test_used_non_pta_cannot_fill_box_pack_pta_query(self):
        self.price(pta_status="non_pta")
        self.assertEqual(self.ask("box pack PTA phone under 80k").data["results"], [])
        self.assertEqual(self.ask("used non PTA phone under 80k").data["results"][0]["market_price"]["pta_status"], "non_pta")

    def test_independently_checked_pta_requires_checked_observation(self):
        self.price()
        self.assertEqual(self.ask("verified PTA gaming phone under 80k").data["results"], [])
        self.price(pta_verification="checked", price_min_pkr=Decimal("68000"))
        response = self.ask("verified PTA gaming phone under 80k")
        self.assertEqual(response.data["results"][0]["market_price"]["pta_verification"], "checked")

    def test_reported_pta_is_not_misrepresented(self):
        self.price()
        response = self.ask("PTA used phone under 80k")
        self.assertIn("reported", " ".join(response.data["results"][0]["tradeoffs"]))

    def test_pending_restricted_stale_and_hidden_data_stay_private(self):
        self.price(source=self.restricted)
        self.price(verification_status=ReviewStatus.PENDING, reviewed_at=None)
        self.price(observed_at=timezone.now() - timedelta(days=40))
        self.price(variant=self.secret_variant)
        IngestionCandidate.objects.create(
            candidate_type=IngestionCandidate.CandidateType.PRICE, source=self.source,
            matched_device=self.a, payload={"confidential_value": "DONT_LEAK"},
        )
        response = self.ask("Best used phone under 80k")
        self.assertEqual(response.data["results"], [])
        self.assertNotIn("DONT_LEAK", str(response.data))

    def test_camera_and_gaming_priorities_change_ranking(self):
        self.price()
        self.price(variant=self.b_variant, price_min_pkr=Decimal("66000"), price_max_pkr=Decimal("72000"))
        camera = self.ask("Best camera used phone under 80k")
        gaming = self.ask("Best gaming used phone under 80k")
        self.assertEqual(camera.data["results"][0]["device"]["slug"], "samsung-lens")
        self.assertEqual(gaming.data["results"][0]["device"]["slug"], "orion-play")

    def test_best_under_one_lac_does_not_reward_cheapest_phone(self):
        """Quality evidence, not unused budget, should determine a generic shortlist."""
        self.price(variant=self.a_high, price_min_pkr=Decimal("95000"), price_max_pkr=Decimal("99000"))
        self.price(variant=self.a_low, price_min_pkr=Decimal("35000"), price_max_pkr=Decimal("40000"))
        self.price(variant=self.b_variant, price_min_pkr=Decimal("85000"), price_max_pkr=Decimal("90000"))
        response = self.ask("tell me about the best phone under 1 lac")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["criteria"]["budget_pkr"], "100000")
        self.assertEqual(response.data["results"][0]["device"]["slug"], "orion-play")
        self.assertIn("provisional", response.data["explanation"].lower()) if response.data["results"][0]["missing_score_evidence"] else self.assertIn("catalog scoring", response.data["explanation"].lower())
        self.assertIn("observed asking", response.data["explanation"].lower())

    def test_missing_scores_do_not_claim_verified_best_phone(self):
        variant = DeviceVariant.objects.create(
            device=self.a, name="16GB/512GB", ram_gb=16, storage_gb=512,
            camera_score=0, gaming_score=0, battery_score=0, display_refresh_hz=0,
        )
        self.price(variant=variant, price_min_pkr=Decimal("80000"), price_max_pkr=Decimal("85000"))
        response = self.ask("best phone under 1 lac")
        self.assertEqual(response.status_code, 200)
        first = response.data["results"][0]
        self.assertIsNone(first["fit_score"])
        self.assertFalse(first["recommended"])
        self.assertIn("provisional", response.data["explanation"].lower())
        self.assertIn("16 GB RAM", response.data["explanation"])

    def test_inferred_brand_is_respected(self):
        self.price()
        self.price(variant=self.b_variant)
        response = self.ask("Best Samsung used camera phone under 80k")
        self.assertEqual([r["device"]["slug"] for r in response.data["results"]], ["samsung-lens"])

    def test_explicit_condition_overrides_message(self):
        self.price()
        self.price(condition="box_pack", grade="", price_min_pkr=Decimal("75000"), price_max_pkr=Decimal("77000"))
        response = self.ask("used phone under 80k", condition="box_pack")
        self.assertEqual(response.data["results"][0]["market_price"]["condition"], "box_pack")

    def test_ambiguous_condition_is_rejected(self):
        response = self.ask("Compare new and used phones under 80k")
        self.assertEqual(response.status_code, 400)
        self.assertIn("condition", str(response.data).lower())

    def test_foreign_currency_is_rejected_not_compared_to_pkr(self):
        response = self.ask("Best used phone under $500")
        self.assertEqual(response.status_code, 400)
        self.assertIn("PKR", str(response.data))

    def test_zero_scores_cannot_be_high_confidence(self):
        DeviceVariant.objects.filter(pk=self.b_variant.pk).update(
            camera_score=0, gaming_score=0, battery_score=0,
        )
        self.price(variant=self.b_variant, price_min_pkr=Decimal("20000"), price_max_pkr=Decimal("25000"))
        self.price(variant=self.a_high)
        response = self.ask("Best gaming phone under 80k")
        self.assertEqual(response.data["results"][0]["device"]["slug"], "orion-play")
        self.assertIsNone(response.data["results"][1]["fit_score"])
        self.assertTrue(response.data["needs_research"])

    def test_no_gemini_or_web_requests_from_local_endpoint(self):
        self.price()
        with patch("recommendations.providers._gemini_client") as gemini:
            response = self.ask("Best used gaming phone under 80k")
        gemini.assert_not_called()
        self.assertEqual(response.data["response_source"], "deterministic")
        self.assertFalse(response.data["research_executed"])

    def test_query_is_logged_without_catalog_mutation(self):
        self.price()
        before_prices = MarketPriceObservation.objects.count()
        response = self.ask("Best used gaming phone under 80k")
        query = RecommendationQuery.objects.get(pk=response.data["query_id"])
        self.assertEqual(query.currency, "PKR")
        self.assertEqual(query.country_code, "PK")
        self.assertEqual(query.budget, Decimal("80000"))
        self.assertEqual(MarketPriceObservation.objects.count(), before_prices)

    def test_very_low_result_count_requests_additional_research(self):
        self.price()
        response = self.ask("Best gaming phone under 80k")
        self.assertEqual(response.data["count"], 1)
        self.assertTrue(response.data["needs_research"])
        self.assertEqual(response.data["research_reason"], "limited_local_evidence")
