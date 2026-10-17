"""Patch 03: Django Admin is an explicit, evidence-aware editing surface."""

from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .admin_forms import (
    DeviceClaimAdminForm,
    IngestionCandidateReviewForm,
    MarketPriceObservationAdminForm,
    ResearchSourceAdminForm,
)
from .models import (
    Brand,
    Device,
    DeviceClaim,
    DeviceVariant,
    IngestionCandidate,
    MarketPriceObservation,
    ResearchSource,
    ReviewStatus,
)


class CatalogAdminWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.brand = Brand.objects.create(name="Example", slug="example")
        cls.device = Device.objects.create(
            name="Test Phone", slug="test-phone", brand=cls.brand,
            is_published=False,
        )
        cls.variant = DeviceVariant.objects.create(
            device=cls.device, name="8/128", ram_gb=8, storage_gb=128,
        )
        cls.source = ResearchSource.objects.create(
            title="Permitted test manufacturer source",
            url="https://example.com/official/specs",
            source_type=ResearchSource.SourceType.MANUFACTURER,
            reuse_status=ResearchSource.ReuseStatus.PERMITTED,
            reuse_notes="Manufacturer technical facts used under approved test policy.",
        )
        cls.unknown_source = ResearchSource.objects.create(
            title="Unknown rights listing", url="https://example.org/listing",
            source_type=ResearchSource.SourceType.CLASSIFIED,
        )
        cls.admin_user = get_user_model().objects.create_superuser(
            username="catalog-admin", email="admin@example.com", password="a-test-password-only"
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def sample_price(self, **overrides):
        params = {
            "variant": self.variant,
            "source": self.source,
            "condition": MarketPriceObservation.Condition.USED,
            "grade": MarketPriceObservation.Grade.GOOD,
            "pta_status": MarketPriceObservation.PTAStatus.NON_PTA,
            "pta_verification": MarketPriceObservation.PTAVerification.REPORTED,
            "price_min_pkr": Decimal("45000"),
            "price_max_pkr": Decimal("50000"),
            "city": "Lahore",
        }
        params.update(overrides)
        return MarketPriceObservation.objects.create(**params)

    def test_all_new_models_are_registered_in_admin(self):
        for model in (ResearchSource, DeviceClaim, IngestionCandidate, MarketPriceObservation):
            response = self.client.get(
                reverse(f"admin:catalog_{model._meta.model_name}_changelist")
            )
            self.assertEqual(response.status_code, 200)

    def test_device_editor_has_variants_images_and_spec_sections(self):
        response = self.client.get(reverse("admin:catalog_device_change", args=[self.device.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RAM/storage variants")
        self.assertContains(response, "specification_sections")
        self.assertContains(response, "images")

    def test_variant_editor_has_pakistan_price_inline(self):
        response = self.client.get(
            reverse("admin:catalog_devicevariant_change", args=[self.variant.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pakistan PKR market observations")
        self.assertContains(response, "pk_market_prices")

    def test_source_permitted_status_requires_written_basis(self):
        form = ResearchSourceAdminForm(data={
            "title": "Example vendor", "url": "https://example.com/vendor",
            "source_type": ResearchSource.SourceType.RETAILER,
            "reuse_status": ResearchSource.ReuseStatus.PERMITTED,
            "reuse_notes": "",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("reuse_notes", form.errors)

    def test_price_review_form_stamps_timestamp_when_verified(self):
        price = self.sample_price()
        form = MarketPriceObservationAdminForm(instance=price, data={
            "variant": self.variant.pk, "source": self.source.pk,
            "condition": "used", "grade": "good", "pta_status": "non_pta",
            "pta_verification": "reported", "price_min_pkr": "45000",
            "price_max_pkr": "50000", "city": "Lahore",
            "observed_at": timezone.localtime(price.observed_at).strftime("%Y-%m-%d %H:%M:%S"),
            "verification_status": "verified", "listing_status": "unknown",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNotNone(form.instance.reviewed_at)

    def test_price_form_rejects_future_observation(self):
        price = self.sample_price()
        form = MarketPriceObservationAdminForm(instance=price, data={
            "variant": self.variant.pk, "source": self.source.pk,
            "condition": "used", "grade": "good", "pta_status": "non_pta",
            "pta_verification": "reported", "price_min_pkr": "45000",
            "price_max_pkr": "50000", "city": "Lahore",
            "observed_at": (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
            "verification_status": "pending", "listing_status": "unknown",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("observed_at", form.errors)

    def test_bulk_verification_rejects_missing_price_evidence(self):
        valid = self.sample_price()
        missing = self.sample_price(source=None, notes="")
        url = reverse("admin:catalog_marketpriceobservation_changelist")
        response = self.client.post(url, {
            "action": "verify_selected", "_selected_action": [valid.pk, missing.pk],
            "select_across": "0", "index": "0",
        })
        self.assertEqual(response.status_code, 302)
        valid.refresh_from_db()
        missing.refresh_from_db()
        self.assertEqual(valid.verification_status, ReviewStatus.VERIFIED)
        self.assertIsNotNone(valid.reviewed_at)
        self.assertEqual(missing.verification_status, ReviewStatus.PENDING)
        self.assertIsNone(missing.reviewed_at)

    def test_research_claim_verification_needs_permitted_source(self):
        allowed = DeviceClaim.objects.create(
            device=self.device, source=self.source,
            field_path="battery_mah", proposed_value=5000,
        )
        unlicensed = DeviceClaim.objects.create(
            device=self.device, source=self.unknown_source,
            field_path="battery_mah", proposed_value=6000,
        )
        url = reverse("admin:catalog_deviceclaim_changelist")
        response = self.client.post(url, {
            "action": "verify_selected", "_selected_action": [allowed.pk, unlicensed.pk],
            "select_across": "0", "index": "0",
        })
        self.assertEqual(response.status_code, 302)
        allowed.refresh_from_db()
        unlicensed.refresh_from_db()
        self.assertEqual(allowed.status, ReviewStatus.VERIFIED)
        self.assertEqual(unlicensed.status, ReviewStatus.PENDING)
        self.assertFalse(self.device.is_published)

    def test_claim_form_refuses_unknown_rights(self):
        claim = DeviceClaim.objects.create(
            device=self.device, source=self.unknown_source,
            field_path="battery_mah", proposed_value=5000,
        )
        form = DeviceClaimAdminForm(instance=claim, data={
            "device": self.device.pk, "source": self.unknown_source.pk,
            "field_path": "battery_mah", "proposed_value": "5000",
            "status": ReviewStatus.VERIFIED,
            "observed_at": timezone.localtime(claim.observed_at).strftime("%Y-%m-%d %H:%M:%S"),
        })
        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_candidate_approval_stages_only_and_does_not_insert_devices(self):
        candidate = IngestionCandidate.objects.create(
            candidate_type=IngestionCandidate.CandidateType.DEVICE,
            source=self.source,
            payload={"name": "AI Discovered Phone", "fake_spec": "untrusted"},
        )
        before = Device.objects.count()
        response = self.client.post(
            reverse("admin:catalog_ingestioncandidate_changelist"),
            {"action": "approve_selected", "_selected_action": [candidate.pk],
             "select_across": "0", "index": "0"},
        )
        self.assertEqual(response.status_code, 302)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, IngestionCandidate.Status.APPROVED)
        self.assertIsNotNone(candidate.reviewed_at)
        self.assertEqual(Device.objects.count(), before)

    def test_candidate_approval_requires_permitted_source(self):
        candidate = IngestionCandidate.objects.create(
            candidate_type="device", source=self.unknown_source,
            payload={"name": "Pending Phone"},
        )
        response = self.client.post(
            reverse("admin:catalog_ingestioncandidate_changelist"),
            {"action": "approve_selected", "_selected_action": [candidate.pk],
             "select_across": "0", "index": "0"},
        )
        self.assertEqual(response.status_code, 302)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, IngestionCandidate.Status.PENDING)

    def test_candidate_payload_is_escaped_not_executed(self):
        candidate = IngestionCandidate.objects.create(
            candidate_type="device", source=self.source,
            payload={"name": "<script>alert('oops')</script>"},
        )
        response = self.client.get(
            reverse("admin:catalog_ingestioncandidate_change", args=[candidate.pk])
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertNotIn("<script>alert('oops')</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_ingested_state_cannot_be_selected_manually(self):
        candidate = IngestionCandidate.objects.create(
            candidate_type="device", source=self.source,
            payload={"name": "Not Yet Imported"},
        )
        form = IngestionCandidateReviewForm(instance=candidate, data={
            "candidate_type": "device", "source": self.source.pk,
            "payload": '{"name": "Not Yet Imported"}',
            "status": IngestionCandidate.Status.INGESTED,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_candidate_creation_is_not_available_in_admin(self):
        response = self.client.get(reverse("admin:catalog_ingestioncandidate_add"))
        self.assertEqual(response.status_code, 403)
