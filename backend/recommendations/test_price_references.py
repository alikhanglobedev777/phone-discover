from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Brand, Device, DeviceVariant, MarketPriceObservation


@override_settings(GEMINI_AUTO_RESEARCH_ENABLED=False)
class ConversationPriceReferenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        brand = Brand.objects.create(name="Samsung", slug="samsung")
        for name, city, price in (("National", "", 70000), ("Expensive", "", 140000), ("Local", "Lahore", 65000)):
            device = Device.objects.create(brand=brand, name=name, slug=name.lower(), is_published=True)
            variant = DeviceVariant.objects.create(device=device, name="8/128", ram_gb=8, storage_gb=128)
            MarketPriceObservation.objects.create(
                variant=variant, condition="box_pack", city=city,
                price_min_pkr=price, price_max_pkr=price, observed_at=timezone.now(),
                verification_status="verified", reviewed_at=timezone.now(), notes="Test price evidence",
            )

    def setUp(self):
        self.client = APIClient()
        throttle = patch("recommendations.views.PakistanConversationView.throttle_classes", [])
        throttle.start()
        self.addCleanup(throttle.stop)

    def ask(self, message, **fields):
        response = self.client.post("/api/recommendations/converse/", {"message": message, **fields}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_karachi_prompt_shows_references_without_claiming_city_match(self):
        response = self.ask("Best box pack camera phone under 120k in Karachi")
        self.assertEqual(response["count"], 0)
        self.assertEqual(response["results"], [])
        reference = response["price_references"]
        self.assertEqual(reference["unconfirmed_filters"], ["city"])
        self.assertEqual([item["device"]["slug"] for item in reference["results"]], ["national"])
        self.assertFalse(reference["results"][0]["recommended"])
        self.assertEqual(reference["results"][0]["market_price"]["city"], "")
        self.assertEqual(response["criteria"]["city"], "Karachi")
        self.assertIn("unconfirmed", reference["notice"])

    def test_remembered_pta_is_explicitly_unconfirmed_in_references(self):
        first = self.ask("Lahore mein 80 hazar tak used PTA approved gaming phone")
        response = self.ask("Best box pack camera phone under 120k in Karachi", session_id=first["session_id"])
        self.assertTrue(response["memory_used"])
        self.assertEqual(response["criteria"]["pta_status"], "approved")
        self.assertIn("pta_status", response["price_references"]["unconfirmed_filters"])
        self.assertEqual(response["price_references"]["results"][0]["market_price"]["pta_status"], "unknown")

    def test_clearing_controls_removes_memory_and_keeps_other_constraints(self):
        first = self.ask("used PTA gaming under 80k in Lahore")
        response = self.ask("show phones", session_id=first["session_id"], city=None,
                            pta_status=None, condition=None, priorities=[])
        self.assertEqual(Decimal(response["criteria"]["budget_pkr"]), 80000)
        self.assertIsNone(response["criteria"]["city"])
        self.assertIsNone(response["criteria"]["pta_status"])
        self.assertIsNone(response["criteria"]["condition"])
        self.assertEqual(response["criteria"]["priorities"], [])
        follow = self.ask("Samsung mein batao", session_id=first["session_id"])
        self.assertIsNone(follow["criteria"]["city"])
        self.assertIsNone(follow["criteria"]["pta_status"])
        self.assertEqual(len(follow["results"]), 2)

    def test_complete_example_reset_discards_previous_pta_brand_and_memory(self):
        first = self.ask("used PTA Samsung phone under 80k in Lahore")
        response = self.ask("Best box pack camera phone under 120k in Karachi",
                            session_id=first["session_id"], reset_context=True)
        self.assertFalse(response["memory_used"])
        self.assertIsNone(response["criteria"]["pta_status"])
        self.assertIsNone(response["criteria"]["brand"])
        self.assertTrue(response["price_references"]["results"])

    def test_references_do_not_relax_budget_memory_brand_or_condition(self):
        for message in ("used phone under 120k in Karachi", "box pack phone under 20k in Karachi",
                        "Xiaomi box pack under 120k in Karachi", "non PTA box pack under 120k in Karachi"):
            with self.subTest(message=message):
                self.assertEqual(self.ask(message)["price_references"]["results"], [])
        self.assertEqual(self.ask("box pack under 120k in Karachi", ram_min=12)["price_references"]["results"], [])

    def test_exact_city_match_remains_primary_without_references(self):
        response = self.ask("box pack phone under 120k in Lahore")
        self.assertEqual(response["results"][0]["device"]["slug"], "local")
        self.assertEqual(response["price_references"]["results"], [])
