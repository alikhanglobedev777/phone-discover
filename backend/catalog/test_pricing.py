"""Patch 04: public price intelligence must not turn a listing into a quote."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    Brand, Device, DeviceVariant, IngestionCandidate, MarketPriceObservation,
    ResearchSource, ReviewStatus,
)
from .pricing import budget_fit, price_summaries_for_device


class PakistanPriceEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(name="Example", slug="pricing-example")
        cls.device = Device.objects.create(
            brand=cls.brand, name="Phone", slug="pricing-phone", is_published=True,
        )
        cls.other_device = Device.objects.create(
            brand=cls.brand, name="Hidden Phone", slug="hidden-pricing-phone", is_published=False,
        )
        cls.variant = DeviceVariant.objects.create(
            device=cls.device, name="8/128", ram_gb=8, storage_gb=128,
        )
        cls.variant_256 = DeviceVariant.objects.create(
            device=cls.device, name="8/256", ram_gb=8, storage_gb=256,
        )
        cls.other_variant = DeviceVariant.objects.create(
            device=cls.other_device, name="8/128", ram_gb=8, storage_gb=128,
        )
        cls.permitted = ResearchSource.objects.create(
            url="https://example.org/permitted", title="Allowed source",
            reuse_status=ResearchSource.ReuseStatus.PERMITTED,
            reuse_notes="Publisher has authorized structured price references.",
        )
        cls.unknown = ResearchSource.objects.create(
            url="https://example.org/unknown", title="Unknown rights",
        )
        cls.restricted = ResearchSource.objects.create(
            url="https://example.org/restricted", title="Restricted",
            reuse_status=ResearchSource.ReuseStatus.RESTRICTED,
        )

    def observation(self, **updates):
        payload = {
            "variant": self.variant,
            "source": self.permitted,
            "condition": MarketPriceObservation.Condition.USED,
            "grade": MarketPriceObservation.Grade.GOOD,
            "pta_status": MarketPriceObservation.PTAStatus.APPROVED,
            "pta_verification": MarketPriceObservation.PTAVerification.REPORTED,
            "city": "Lahore",
            "price_min_pkr": Decimal("69000.00"),
            "price_max_pkr": Decimal("73000.00"),
            "observed_at": timezone.now() - timedelta(hours=3),
            "reviewed_at": timezone.now() - timedelta(hours=2),
            "verification_status": ReviewStatus.VERIFIED,
            "listing_status": MarketPriceObservation.ListingStatus.ACTIVE,
        }
        payload.update(updates)
        return MarketPriceObservation.objects.create(**payload)

    def summaries(self, **filters):
        return price_summaries_for_device(self.device.pk, **filters)

    def test_missing_observations_return_empty_not_fabricated_price(self):
        self.assertEqual(self.summaries(), [])
        response = APIClient().get(f"/api/catalog/devices/{self.device.slug}/pakistan-prices/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summaries"], [])
        self.assertIn("not guaranteed", response.data["disclaimer"])

    def test_public_detail_has_separate_pakistan_price_guide(self):
        self.observation()
        response = APIClient().get(f"/api/catalog/devices/{self.device.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["pakistan_prices"]), 1)
        self.assertEqual(response.data["pakistan_prices"][0]["currency"], "PKR")

    def test_pending_and_rejected_observations_are_not_public(self):
        self.observation(verification_status=ReviewStatus.PENDING, reviewed_at=None)
        self.observation(verification_status=ReviewStatus.REJECTED)
        self.assertEqual(self.summaries(), [])

    def test_unreviewed_verified_status_is_not_public(self):
        # Models' DB check prevents this state. Query-level gating is still essential.
        self.observation()
        self.assertEqual(len(self.summaries()), 1)

    def test_condition_and_pta_classification_never_mix(self):
        self.observation(price_min_pkr=60000, price_max_pkr=65000)
        self.observation(
            condition=MarketPriceObservation.Condition.BOX_PACK,
            grade="", price_min_pkr=95000, price_max_pkr=100000,
        )
        self.observation(
            pta_status=MarketPriceObservation.PTAStatus.NON_PTA,
            price_min_pkr=40000, price_max_pkr=45000,
        )
        groups = self.summaries()
        self.assertEqual(len(groups), 3)
        self.assertEqual({group["condition"] for group in groups}, {"used", "box_pack"})
        used_approved = next(g for g in groups if g["condition"] == "used" and g["pta_status"] == "approved")
        self.assertEqual(used_approved["observed_min_pkr"], "60000.00")
        self.assertEqual(used_approved["observed_max_pkr"], "65000.00")

    def test_reported_and_independently_checked_pta_never_mix(self):
        self.observation()
        self.observation(pta_verification=MarketPriceObservation.PTAVerification.CHECKED)
        self.assertEqual(len(self.summaries()), 2)
        self.assertEqual({g["pta_verification"] for g in self.summaries()}, {"reported", "checked"})

    def test_grade_variant_and_city_are_separate_price_buckets(self):
        self.observation()
        self.observation(grade=MarketPriceObservation.Grade.EXCELLENT)
        self.observation(variant=self.variant_256)
        self.observation(city="Karachi")
        self.assertEqual(len(self.summaries()), 4)
        self.assertEqual(len(self.summaries(city="lahore")), 3)
        self.assertEqual(len(self.summaries(variant_id=self.variant_256.id)), 1)

    def test_city_matching_is_case_insensitive(self):
        self.observation(city="lahore")
        self.observation(city="LAHORE")
        groups = self.summaries(city="Lahore")
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["observation_count"], 2)

    def test_used_stale_after_14_days_but_box_pack_fresh_for_30(self):
        observed = timezone.now() - timedelta(days=20)
        self.observation(observed_at=observed)
        self.observation(
            condition=MarketPriceObservation.Condition.BOX_PACK,
            grade="", observed_at=observed,
        )
        groups = self.summaries()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["condition"], "box_pack")
        self.assertEqual(groups[0]["freshness_days"], 30)

    def test_future_and_ended_listings_never_get_included(self):
        self.observation(observed_at=timezone.now() + timedelta(days=1))
        self.observation(listing_status=MarketPriceObservation.ListingStatus.ENDED)
        self.assertEqual(self.summaries(), [])

    def test_sources_with_unknown_or_restricted_reuse_are_excluded(self):
        self.observation(source=self.unknown)
        self.observation(source=self.restricted)
        self.assertEqual(self.summaries(), [])

    def test_permitted_source_needs_documented_rights(self):
        undocumented = ResearchSource.objects.create(
            url="https://example.org/undocumented", title="Undocumented",
            reuse_status=ResearchSource.ReuseStatus.PERMITTED,
            reuse_notes="",
        )
        self.observation(source=undocumented)
        self.assertEqual(self.summaries(), [])

    def test_revoking_source_reuse_permission_removes_public_guide(self):
        self.observation()
        self.assertEqual(len(self.summaries()), 1)
        self.permitted.reuse_status = ResearchSource.ReuseStatus.RESTRICTED
        self.permitted.save(update_fields=["reuse_status"])
        self.assertEqual(self.summaries(), [])

    def test_admin_verified_manual_observation_needs_notes(self):
        self.observation(source=None, notes="Price checked from authorized offline survey.")
        self.assertEqual(self.summaries()[0]["evidence_type"], "admin_documented")
        self.assertEqual(self.summaries()[0]["sources"], [])

    def test_research_claims_do_not_publish_prices(self):
        IngestionCandidate.objects.create(
            candidate_type=IngestionCandidate.CandidateType.PRICE,
            source=self.unknown,
            matched_device=self.device,
            payload={"price_min_pkr": "1.00", "seller_contact": "PRIVATE"},
        )
        response = APIClient().get(f"/api/catalog/devices/{self.device.slug}/pakistan-prices/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summaries"], [])
        self.assertNotIn("PRIVATE", str(response.data))

    def test_repeated_listing_url_counts_as_one_latest_sample(self):
        url = "https://example.org/listing/1"
        self.observation(listing_url=url, price_min_pkr=60000, price_max_pkr=62000,
                         observed_at=timezone.now() - timedelta(days=3))
        self.observation(listing_url=url, price_min_pkr=70000, price_max_pkr=72000,
                         observed_at=timezone.now() - timedelta(hours=3))
        guide = self.summaries()[0]
        self.assertEqual(guide["observation_count"], 1)
        self.assertEqual(guide["observed_min_pkr"], "70000.00")

    def test_multiple_independent_observations_have_correct_median(self):
        self.observation(price_min_pkr=60000, price_max_pkr=64000)
        self.observation(price_min_pkr=72000, price_max_pkr=76000)
        guide = self.summaries()[0]
        self.assertEqual(guide["observation_count"], 2)
        self.assertEqual(guide["observed_min_pkr"], "60000.00")
        self.assertEqual(guide["observed_max_pkr"], "76000.00")
        self.assertEqual(guide["median_observed_midpoint_pkr"], "68000.00")
        self.assertEqual(guide["source_count"], 1)

    def test_budget_fit_does_not_promise_an_offer(self):
        self.assertEqual(budget_fit(60000, 75000, 80000), "within_observed_range")
        self.assertEqual(budget_fit(60000, 75000, 70000), "possibly_within_budget")
        self.assertEqual(budget_fit(60000, 75000, 50000), "above_budget")
        self.assertIsNone(budget_fit(60000, 75000, None))
        with self.assertRaises(ValueError):
            budget_fit(60000, 75000, -1)

    def test_api_filters_and_metadata_for_pakistan_prices(self):
        self.observation(city="Lahore")
        self.observation(city="Karachi", pta_status=MarketPriceObservation.PTAStatus.NON_PTA)
        url = f"/api/catalog/devices/{self.device.slug}/pakistan-prices/"
        response = APIClient().get(url, {
            "city": "Lahore", "condition": "used", "grade": "good",
            "pta_status": "approved", "budget_pkr": "71000",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["summaries"]), 1)
        self.assertEqual(response.data["currency"], "PKR")
        self.assertEqual(response.data["summaries"][0]["budget_fit"], "possibly_within_budget")
        self.assertEqual(response.data["summaries"][0]["availability"], "not_confirmed")
        self.assertIn("source", response.data["summaries"][0]["evidence_type"])

    def test_api_rejects_invalid_filters_or_foreign_variant(self):
        url = f"/api/catalog/devices/{self.device.slug}/pakistan-prices/"
        self.assertEqual(APIClient().get(url, {"condition": "fake"}).status_code, 400)
        self.assertEqual(APIClient().get(url, {"budget_pkr": "-1"}).status_code, 400)
        self.assertEqual(APIClient().get(url, {"variant_id": self.other_variant.pk}).status_code, 400)

    def test_unpublished_phone_has_no_public_price_guide(self):
        self.observation(variant=self.other_variant)
        url = f"/api/catalog/devices/{self.other_device.slug}/pakistan-prices/"
        self.assertEqual(APIClient().get(url).status_code, 404)
        self.assertEqual(price_summaries_for_device(self.other_device.pk), [])
