"""Patch 05: DB-first catalog retrieval must not fabricate or cross-join results."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    Brand, Device, DeviceVariant, IngestionCandidate, MarketPriceObservation,
    ResearchSource, ReviewStatus,
)


class LocalSearchApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(name="Orion", slug="orion")
        cls.other_brand = Brand.objects.create(name="Zenith", slug="zenith")
        cls.phone = Device.objects.create(
            brand=cls.brand, name="Prime Pro", slug="prime-pro", is_published=True,
            status=Device.Status.AVAILABLE, operating_system="Android 16",
        )
        cls.other_phone = Device.objects.create(
            brand=cls.other_brand, name="Gaming", slug="gaming-phone", is_published=True,
            status=Device.Status.AVAILABLE,
        )
        cls.hidden_phone = Device.objects.create(
            brand=cls.brand, name="Secret", slug="hidden-secret", is_published=False,
        )
        cls.low = DeviceVariant.objects.create(
            device=cls.phone, name="6/128", ram_gb=6, storage_gb=128,
            camera_score=75, gaming_score=50, battery_score=60,
        )
        cls.high = DeviceVariant.objects.create(
            device=cls.phone, name="12/256", ram_gb=12, storage_gb=256,
            camera_score=92, gaming_score=85, battery_score=80,
        )
        cls.gaming = DeviceVariant.objects.create(
            device=cls.other_phone, name="8/256", ram_gb=8, storage_gb=256,
            camera_score=65, gaming_score=98, battery_score=82,
        )
        cls.secret = DeviceVariant.objects.create(
            device=cls.hidden_phone, name="8/128", ram_gb=8, storage_gb=128,
        )
        cls.source = ResearchSource.objects.create(
            url="https://example.org/authorized", title="Allowed prices",
            reuse_status=ResearchSource.ReuseStatus.PERMITTED,
            reuse_notes="Permission to reuse structured observed prices for this demo.",
        )
        cls.restricted = ResearchSource.objects.create(
            url="https://example.org/restricted2", title="Restricted prices",
            reuse_status=ResearchSource.ReuseStatus.RESTRICTED,
        )

    def setUp(self):
        self.client = APIClient()

    def price(self, variant=None, **changes):
        values = {
            "variant": variant or self.low,
            "source": self.source,
            "condition": MarketPriceObservation.Condition.USED,
            "grade": MarketPriceObservation.Grade.GOOD,
            "pta_status": MarketPriceObservation.PTAStatus.APPROVED,
            "pta_verification": MarketPriceObservation.PTAVerification.REPORTED,
            "city": "Lahore",
            "price_min_pkr": Decimal("65000.00"),
            "price_max_pkr": Decimal("68000.00"),
            "observed_at": timezone.now() - timedelta(hours=4),
            "reviewed_at": timezone.now() - timedelta(hours=3),
            "verification_status": ReviewStatus.VERIFIED,
            "listing_status": MarketPriceObservation.ListingStatus.ACTIVE,
        }
        values.update(changes)
        return MarketPriceObservation.objects.create(**values)

    def search(self, params=None):
        return self.client.get("/api/catalog/search/", params or {})

    def test_missing_price_evidence_requests_research(self):
        response = self.search()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        self.assertTrue(response.data["needs_research"])
        self.assertEqual(response.data["results"], [])

    def test_valid_evidence_returns_exact_variant_and_internal_link(self):
        self.price()
        response = self.search({"budget_pkr": "80000", "pta_status": "approved", "city": "lahore"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        card = response.data["results"][0]
        self.assertEqual(card["slug"], "prime-pro")
        self.assertEqual(card["variant"]["id"], self.low.id)
        self.assertEqual(card["detail_api_url"], "/api/catalog/devices/prime-pro/")
        self.assertEqual(card["price_observation"]["currency"], "PKR")
        self.assertEqual(card["price_observation"]["budget_fit"], "within_observed_range")
        self.assertEqual(card["price_observation"]["availability"], "not_confirmed")
        self.assertFalse(response.data["needs_research"])

    def test_ram_and_price_cannot_match_different_variants(self):
        self.price(variant=self.low, price_min_pkr=43000, price_max_pkr=45000)
        self.price(variant=self.high, price_min_pkr=90000, price_max_pkr=93000)
        response = self.search({"ram_min": 12, "budget_pkr": 50000})
        self.assertEqual(response.data["count"], 0)

    def test_storage_and_score_must_match_price_variant(self):
        self.price(variant=self.low)
        self.price(variant=self.high, price_min_pkr=100000, price_max_pkr=102000)
        response = self.search({"storage_min": 256, "camera_min": 90, "budget_pkr": 70000})
        self.assertEqual(response.data["count"], 0)

    def test_strict_budget_uses_max_not_min(self):
        self.price(price_min_pkr=60000, price_max_pkr=75000)
        self.assertEqual(self.search({"budget_pkr": 70000}).data["count"], 0)
        self.assertEqual(self.search({"budget_pkr": 70000, "budget_mode": "possible"}).data["count"], 1)

    def test_used_new_and_pta_records_are_not_interchangeable(self):
        self.price()
        self.price(variant=self.high, condition="box_pack", grade="", pta_status="non_pta")
        self.assertEqual(self.search({"condition": "box_pack", "pta_status": "approved"}).data["count"], 0)
        self.assertEqual(self.search({"condition": "box_pack", "pta_status": "non_pta"}).data["count"], 1)

    def test_reported_pta_is_not_independently_checked(self):
        self.price()
        self.assertEqual(self.search({"pta_verification": "checked"}).data["count"], 0)
        self.assertEqual(self.search({"pta_verification": "reported"}).data["count"], 1)

    def test_inactive_future_and_stale_prices_are_excluded(self):
        self.price(observed_at=timezone.now() - timedelta(days=16))
        self.price(observed_at=timezone.now() + timedelta(days=1))
        self.price(listing_status="ended")
        self.assertEqual(self.search().data["count"], 0)

    def test_pending_rejected_and_unreviewed_are_excluded(self):
        self.price(verification_status=ReviewStatus.PENDING, reviewed_at=None)
        self.price(verification_status=ReviewStatus.REJECTED)
        self.assertEqual(self.search().data["count"], 0)

    def test_restricted_source_and_blank_manual_notes_are_excluded(self):
        self.price(source=self.restricted)
        self.price(source=None, notes="   ")
        self.assertEqual(self.search().data["count"], 0)

    def test_revoked_source_permission_disappears(self):
        self.price()
        self.assertEqual(self.search().data["count"], 1)
        self.source.reuse_status = ResearchSource.ReuseStatus.RESTRICTED
        self.source.save(update_fields=["reuse_status"])
        self.assertEqual(self.search().data["count"], 0)

    def test_admin_documented_price_has_no_source_url(self):
        self.price(source=None, notes="From documented authorized offline survey")
        self.assertIsNone(self.search().data["results"][0]["price_observation"]["source_url"])

    def test_hidden_phone_and_research_candidate_never_appear(self):
        self.price(variant=self.secret)
        IngestionCandidate.objects.create(
            candidate_type=IngestionCandidate.CandidateType.PRICE,
            source=self.source, matched_device=self.phone,
            payload={"price_min_pkr": "1.00", "private_contact": "SECRET"},
        )
        response = self.search()
        self.assertEqual(response.data["count"], 0)
        self.assertNotIn("SECRET", str(response.data))

    def test_one_device_card_even_if_multiple_variants_qualify(self):
        self.price(variant=self.low, price_max_pkr=75000)
        self.price(variant=self.high, price_min_pkr=65000, price_max_pkr=69000)
        response = self.search()
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["variant"]["id"], self.high.pk)

    def test_sort_by_gaming_changes_order(self):
        self.price(variant=self.low)
        self.price(variant=self.gaming, price_min_pkr=90000, price_max_pkr=95000)
        response = self.search({"sort": "gaming"})
        self.assertEqual([r["slug"] for r in response.data["results"]], ["gaming-phone", "prime-pro"])

    def test_brand_name_and_os_queries(self):
        self.price(variant=self.low)
        self.price(variant=self.gaming)
        response = self.search({"q": "Orion Prime", "os": "android", "brand": "orion"})
        self.assertEqual([r["slug"] for r in response.data["results"]], ["prime-pro"])

    def test_page_size_pagination_and_total_count(self):
        self.price(variant=self.low)
        self.price(variant=self.gaming)
        first = self.search({"page_size": 1, "page": 1})
        second = self.search({"page_size": 1, "page": 2})
        self.assertEqual(first.data["count"], 2)
        self.assertEqual(len(first.data["results"]), 1)
        self.assertTrue(first.data["has_more"])
        self.assertEqual(len(second.data["results"]), 1)
        self.assertFalse(second.data["has_more"])
        self.assertNotEqual(first.data["results"][0]["slug"], second.data["results"][0]["slug"])

    def test_specs_only_query_does_not_claim_a_price(self):
        response = self.search({"q": "Prime", "require_price": "false", "ram_min": 12})
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["variant"]["id"], self.high.pk)
        self.assertIsNone(response.data["results"][0]["price_observation"])

    def test_bad_filters_return_400(self):
        for params in (
            {"budget_pkr": "-1"}, {"condition": "not_real"}, {"page_size": "999"},
            {"grade": "good"}, {"require_price": "false", "budget_pkr": "90000"},
            {"pta_status": "unknown", "pta_verification": "checked"},
            {"camera_min": "101"}, {"sort": "random"},
        ):
            with self.subTest(params=params):
                self.assertEqual(self.search(params).status_code, 400)
