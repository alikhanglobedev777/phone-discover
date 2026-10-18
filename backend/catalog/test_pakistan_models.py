"""Patch 02 regression tests: Pakistan market data remains evidence-gated."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    Brand,
    Device,
    DeviceClaim,
    DeviceVariant,
    IngestionCandidate,
    MarketOffer,
    MarketPriceObservation,
    ResearchSource,
    ReviewStatus,
)


class PakistanMarketSchemaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(name="Example", slug="example")
        cls.device = Device.objects.create(
            brand=cls.brand, name="Test Handset", slug="test-handset", is_published=True
        )
        cls.variant = DeviceVariant.objects.create(
            device=cls.device, name="8/128", ram_gb=8, storage_gb=128
        )
        cls.source = ResearchSource.objects.create(
            title="Public example", url="https://example.com/sample/phone",
            source_type=ResearchSource.SourceType.CLASSIFIED,
        )

    def observation(self, **overrides):
        data = {
            "variant": self.variant,
            "source": self.source,
            "condition": MarketPriceObservation.Condition.USED,
            "grade": MarketPriceObservation.Grade.GOOD,
            "pta_status": MarketPriceObservation.PTAStatus.NON_PTA,
            "pta_verification": MarketPriceObservation.PTAVerification.REPORTED,
            "city": "Gujranwala",
            "price_min_pkr": Decimal("45000.00"),
            "price_max_pkr": Decimal("49000.00"),
        }
        data.update(overrides)
        return MarketPriceObservation(**data)

    def test_used_non_pta_observation_is_saved_separately_from_legacy_offer(self):
        legacy = MarketOffer.objects.create(
            variant=self.variant, country_code="PK", currency="PKR",
            price="78000", seller_name="Historical dealer",
            product_url="https://example.com/legacy-offer",
        )
        record = self.observation()
        record.full_clean()
        record.save()
        self.assertEqual(record.verification_status, ReviewStatus.PENDING)
        self.assertEqual(record.pta_status, MarketPriceObservation.PTAStatus.NON_PTA)
        self.assertEqual(record.city, "Gujranwala")
        legacy.refresh_from_db()
        self.assertEqual(legacy.price, Decimal("78000.00"))
        self.assertEqual(self.variant.pk_market_prices.count(), 1)

    def test_invalid_price_ranges_rejected_by_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.observation(price_min_pkr=Decimal("80000"), price_max_pkr=Decimal("79000")).save()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.observation(price_min_pkr=Decimal("0"), price_max_pkr=Decimal("100")).save()

    def test_condition_grade_is_not_applicable_to_box_pack(self):
        record = self.observation(condition=MarketPriceObservation.Condition.BOX_PACK)
        with self.assertRaises(ValidationError):
            record.full_clean()

    def test_independently_checked_pta_cannot_be_unknown(self):
        record = self.observation(
            pta_status=MarketPriceObservation.PTAStatus.UNKNOWN,
            pta_verification=MarketPriceObservation.PTAVerification.CHECKED,
        )
        with self.assertRaises(ValidationError):
            record.full_clean()

    def test_verified_price_requires_review_timestamp_and_evidence(self):
        record = self.observation(verification_status=ReviewStatus.VERIFIED)
        with self.assertRaises(ValidationError):
            record.full_clean()
        record.reviewed_at = timezone.now()
        record.full_clean()
        record.source = None
        with self.assertRaises(ValidationError):
            record.full_clean()

    def test_source_url_is_unique_and_default_reuse_rights_are_unknown(self):
        self.assertEqual(self.source.reuse_status, ResearchSource.ReuseStatus.UNKNOWN)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ResearchSource.objects.create(
                    title="Same link", url=self.source.url,
                )

    def test_claim_requires_source_and_review_for_verification(self):
        claim = DeviceClaim(
            device=self.device, source=self.source, field_path="battery_mah",
            proposed_value=5000,
        )
        claim.full_clean()
        claim.save()
        self.assertEqual(claim.status, ReviewStatus.PENDING)
        claim.status = ReviewStatus.VERIFIED
        with self.assertRaises(ValidationError):
            claim.full_clean()
        claim.reviewed_at = timezone.now()
        claim.full_clean()

    def test_candidates_start_pending_and_reject_unstructured_payload(self):
        candidate = IngestionCandidate.objects.create(
            candidate_type=IngestionCandidate.CandidateType.DEVICE,
            source=self.source,
            payload={"model": "Example Test Handset", "ram_gb": 8},
        )
        self.assertEqual(candidate.status, IngestionCandidate.Status.PENDING)
        candidate.payload = ["not a dict"]
        with self.assertRaises(ValidationError):
            candidate.full_clean()

    def test_pending_research_never_leaks_through_existing_public_detail(self):
        IngestionCandidate.objects.create(
            candidate_type=IngestionCandidate.CandidateType.PRICE,
            source=self.source,
            matched_device=self.device,
            payload={"unverified_private_note": "DO_NOT_PUBLISH"},
        )
        record = self.observation()
        record.save()
        response = APIClient().get(f"/api/catalog/devices/{self.device.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("pk_market_prices", response.data["variants"][0])
        self.assertNotIn("ingestion_candidates", response.data)
        self.assertNotIn("DO_NOT_PUBLISH", str(response.data))

    def test_bulk_write_cannot_mark_research_verified_without_review(self):
        claim = DeviceClaim.objects.create(
            device=self.device, source=self.source, field_path="camera.main_mp",
            proposed_value=50,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DeviceClaim.objects.filter(pk=claim.pk).update(status=ReviewStatus.VERIFIED)

    def test_bulk_write_cannot_claim_box_pack_grade_as_used_grade(self):
        record = self.observation()
        record.save()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MarketPriceObservation.objects.filter(pk=record.pk).update(
                    condition=MarketPriceObservation.Condition.BOX_PACK,
                )

    def test_candidate_requires_review_timestamp_before_approval(self):
        candidate = IngestionCandidate.objects.create(
            candidate_type=IngestionCandidate.CandidateType.DEVICE,
            source=self.source,
            payload={"name": "Example"},
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                IngestionCandidate.objects.filter(pk=candidate.pk).update(
                    status=IngestionCandidate.Status.APPROVED,
                )
