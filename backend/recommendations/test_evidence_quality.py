"""Stages 5/6: source provenance, exact factual comparisons and evidence coverage."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from catalog.models import (
    Brand, Device, DeviceVariant, ResearchSource, DeviceClaim, ReviewStatus,
    MarketPriceObservation,
)
from catalog.quality import catalog_quality_snapshot, CACHE_KEY
from .evidence_quality import public_source_url, public_evidence, factual_comparison
from .catalog_advisor import compare_catalog_phones, specs_recommendations


@override_settings(GEMINI_AUTO_RESEARCH_ENABLED=False, GEMINI_WEB_RESEARCH_ENABLED=False)
class EvidenceQualityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        brand = Brand.objects.create(name="Test Brand", slug="test-brand")
        cls.one = Device.objects.create(
            brand=brand, name="Model 11 Ultra", slug="model-11-ultra",
            official_url="https://example.com/manufacturer/model11", is_published=True,
        )
        cls.two = Device.objects.create(
            brand=brand, name="Model 12 Pro", slug="model-12-pro", is_published=True,
        )
        cls.hidden = Device.objects.create(
            brand=brand, name="Unpublished Model", slug="hidden", is_published=False,
        )
        cls.v1 = DeviceVariant.objects.create(
            device=cls.one, name="8GB/128GB", ram_gb=8, storage_gb=128,
            chipset="Chip A", battery_mah=5000, display_refresh_hz=120,
        )
        cls.v2 = DeviceVariant.objects.create(
            device=cls.two, name="8GB/128GB", ram_gb=8, storage_gb=128,
            chipset="Chip B", battery_mah=4500, display_refresh_hz=90,
        )
        cls.source = ResearchSource.objects.create(
            url="https://example.org/review", title="Source reviewed for battery",
            source_type=ResearchSource.SourceType.REVIEW,
            reuse_status=ResearchSource.ReuseStatus.PERMITTED,
            reuse_notes="Source permissions reviewed for this test",
            last_checked_at=timezone.now(),
        )

    def setUp(self):
        cache.delete(CACHE_KEY)

    def test_source_url_filters_unsafe_and_local_links(self):
        for uri in ("javascript:alert(1)", "http://example.com",
                    "https://localhost/path", "https://127.0.0.1",
                    "https://user:pass@example.com", "https://intranet.local"):
            self.assertIsNone(public_source_url(uri))
        self.assertEqual(public_source_url("https://example.com/model"),
                         "https://example.com/model")

    def test_unreviewed_manufacturer_url_is_not_verified_fact(self):
        value = public_evidence(self.one)
        self.assertEqual(value["tier"], "catalog_unverified")
        self.assertEqual(value["reviewed_claims"], 0)
        self.assertEqual(value["source_links"][0]["kind"], "manufacturer_link")

    def test_recent_reviewed_claim_and_stale_claim_have_distinct_tiers(self):
        claim = DeviceClaim.objects.create(
            device=self.one, source=self.source, field_path="battery_mah",
            proposed_value=5000, status=ReviewStatus.VERIFIED,
            reviewed_at=timezone.now(),
        )
        self.assertEqual(public_evidence(self.one)["tier"], "reviewed_recent")
        self.source.last_checked_at = timezone.now() - timedelta(days=400)
        self.source.save(update_fields=["last_checked_at"])
        self.assertEqual(public_evidence(self.one)["tier"], "reviewed_outdated")
        claim.status = ReviewStatus.REJECTED
        claim.save(update_fields=["status"])
        self.assertEqual(public_evidence(self.one)["tier"], "catalog_unverified")

    def test_hardware_facts_never_establish_performance_winner(self):
        facts = factual_comparison(self.v1, self.v2)
        battery = next(row for row in facts if row["field"] == "battery_mah")
        self.assertEqual((battery["first"], battery["second"]), ("5000 mAh", "4500 mAh"))
        self.assertIsNone(battery["higher_spec_slug"])
        comparison = compare_catalog_phones(["model-11-ultra", "model-12-pro"])
        self.assertEqual(len(comparison["hardware_facts"]), 5)
        self.assertTrue(all(row["leader_slug"] is None
                            for row in comparison["dimensions"]))
        self.assertEqual(comparison["market_price_comparison"]["status"],
                         "not_comparable")

    def test_no_price_comparison_for_mismatched_pta_status(self):
        for variant, pta in ((self.v1, "approved"), (self.v2, "non_pta")):
            MarketPriceObservation.objects.create(
                variant=variant, source=self.source, condition="used",
                grade="good", city="Lahore", pta_status=pta,
                pta_verification="reported",
                price_min_pkr=Decimal("60000"), price_max_pkr=Decimal("65000"),
                observed_at=timezone.now(), reviewed_at=timezone.now(),
                verification_status=ReviewStatus.VERIFIED, listing_status="active",
            )
        value = compare_catalog_phones(["model-11-ultra", "model-12-pro"])
        self.assertEqual(value["market_price_comparison"]["status"], "not_comparable")

    def test_source_based_price_comparison_requires_nonoverlapping_ranges(self):
        price = MarketPriceObservation.objects.create(
            variant=self.v1, source=self.source, condition="used", grade="good",
            city="Lahore", pta_status="approved", pta_verification="reported",
            price_min_pkr=Decimal("60000"), price_max_pkr=Decimal("65000"),
            observed_at=timezone.now(), reviewed_at=timezone.now(),
            verification_status=ReviewStatus.VERIFIED, listing_status="active",
        )
        MarketPriceObservation.objects.create(
            variant=self.v2, source=self.source, condition="used", grade="good",
            city="Lahore", pta_status="approved", pta_verification="reported",
            price_min_pkr=Decimal("90000"), price_max_pkr=Decimal("95000"),
            observed_at=timezone.now(), reviewed_at=timezone.now(),
            verification_status=ReviewStatus.VERIFIED, listing_status="active",
        )
        result = compare_catalog_phones(["model-11-ultra", "model-12-pro"])
        price_compare = result["market_price_comparison"]
        self.assertEqual(price_compare["status"], "comparable_observations")
        self.assertEqual(price_compare["lower_observed_price_slug"], "model-11-ultra")
        self.assertIn("not live stock", price_compare["note"])
        price.price_max_pkr = Decimal("100000")
        price.save(update_fields=["price_max_pkr"])
        result = compare_catalog_phones(["model-11-ultra", "model-12-pro"])
        self.assertIsNone(result["market_price_comparison"]["lower_observed_price_slug"])

    def test_catalog_quality_snapshot_reflects_actual_reviewed_evidence(self):
        first = catalog_quality_snapshot()
        self.assertEqual(first["published_devices"], 2)
        self.assertEqual(first["published_variants"], 2)
        self.assertEqual(first["reviewed_source_claims"], 0)
        self.assertEqual(first["variants_with_camera_editorial_score"], 0)
        DeviceClaim.objects.create(
            device=self.one, source=self.source, field_path="chipset",
            proposed_value="Chip A", status=ReviewStatus.VERIFIED,
            reviewed_at=timezone.now(),
        )
        cache.delete(CACHE_KEY)
        self.assertEqual(catalog_quality_snapshot()["reviewed_source_claims"], 1)
