"""Patches 09+10: grounded research -> review -> guarded price observation."""
import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import (
    Brand, Device, DeviceVariant, IngestionCandidate,
    MarketPriceObservation, ResearchSource,
)
from catalog.research_ingestion import stage_grounded_price_leads, promote_approved_price_candidate
from .models import ResearchJob
from .tasks import run_research_job


class ResearchPipelineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        brand = Brand.objects.create(name="Samsung", slug="samsung")
        cls.device = Device.objects.create(
            brand=brand, name="Galaxy Test", slug="samsung-galaxy-test", is_published=True
        )
        cls.variant = DeviceVariant.objects.create(
            device=cls.device, name="8/128", ram_gb=8, storage_gb=128,
        )

    def lead(self, **changes):
        values = {
            "type": "price", "source_url": "https://prices.example.org/listing/1",
            "device_slug": self.device.slug, "variant_name": self.variant.name,
            "condition": "used", "grade": "good", "pta_status": "approved",
            "city": "Lahore", "price_min_pkr": 65000, "price_max_pkr": 70000,
        }
        values.update(changes)
        return values

    def preview(self, proposals=None, **changes):
        result = {
            "status": "grounded_preview",
            "summary": json.dumps({"proposals": proposals if proposals is not None else [self.lead()]}),
            "sources": [{"url": "https://prices.example.org/listing/1", "title": "Price listing"}],
        }
        result.update(changes)
        return result

    def test_stages_pending_price_only_with_unknown_rights(self):
        result = stage_grounded_price_leads(self.preview())
        self.assertEqual(result, {"staged": 1, "duplicates": 0, "rejected": 0})
        source = ResearchSource.objects.get()
        self.assertEqual(source.reuse_status, "unknown")
        lead = IngestionCandidate.objects.get()
        self.assertEqual(lead.status, "pending")
        self.assertEqual(lead.candidate_type, "price")
        self.assertEqual(lead.payload["pta_verification"], "reported")
        self.assertEqual(MarketPriceObservation.objects.count(), 0)

    def test_same_grounded_lead_is_idempotent(self):
        stage_grounded_price_leads(self.preview())
        result = stage_grounded_price_leads(self.preview())
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(IngestionCandidate.objects.count(), 1)
        self.assertEqual(ResearchSource.objects.count(), 1)

    def test_rejects_forged_source_url(self):
        preview = self.preview([self.lead(source_url="https://evil.example.com/another")])
        self.assertEqual(stage_grounded_price_leads(preview)["rejected"], 1)
        self.assertFalse(IngestionCandidate.objects.exists())

    def test_rejects_http_and_localhost_citations(self):
        for url in ["http://example.org/", "https://127.0.0.1/", "https://localhost/"]:
            with self.subTest(url=url):
                lead = self.lead(source_url=url)
                self.assertEqual(stage_grounded_price_leads(self.preview([lead], sources=[{"url": url}] ))["staged"], 0)
        self.assertFalse(ResearchSource.objects.exists())

    def test_rejects_reversed_or_nonpositive_or_unbounded_prices(self):
        for minimum, maximum in [(80000, 70000), (0, 70000), (65000, 99000000), ("nan", "70000")]:
            with self.subTest(minimum=minimum, maximum=maximum):
                preview = self.preview([self.lead(price_min_pkr=minimum, price_max_pkr=maximum)])
                self.assertEqual(stage_grounded_price_leads(preview)["rejected"], 1)
        self.assertFalse(IngestionCandidate.objects.exists())

    def test_rejects_unknown_variant_and_untrusted_pta_grades(self):
        invalid = [self.lead(variant_name="16/512"), self.lead(pta_status="officially_checked"),
                   self.lead(condition="box_pack", grade="good")]
        self.assertEqual(stage_grounded_price_leads(self.preview(invalid))["rejected"], 3)
        self.assertFalse(IngestionCandidate.objects.exists())

    def test_rejects_oversized_proposal_batch_and_plain_text(self):
        self.assertEqual(stage_grounded_price_leads(self.preview([self.lead()] * 9))["staged"], 0)
        self.assertEqual(stage_grounded_price_leads(self.preview(summary="I found a Samsung phone"))["staged"], 0)
        self.assertEqual(stage_grounded_price_leads(self.preview(status="unavailable"))["staged"], 0)
        self.assertFalse(IngestionCandidate.objects.exists())

    def _approved(self, reuse="permitted"):
        stage_grounded_price_leads(self.preview())
        candidate = IngestionCandidate.objects.get()
        candidate.source.reuse_status = reuse
        candidate.source.reuse_notes = "Explicit editorial review of reuse rights" if reuse == "permitted" else ""
        candidate.source.save(update_fields=["reuse_status", "reuse_notes"])
        candidate.status = "approved"
        candidate.reviewed_at = timezone.now()
        candidate.save(update_fields=["status", "reviewed_at"])
        return candidate

    def test_cannot_promote_without_rights(self):
        lead = self._approved(reuse="unknown")
        self.assertFalse(promote_approved_price_candidate(lead.pk))
        self.assertFalse(MarketPriceObservation.objects.exists())

    def test_cannot_promote_pending_or_unreviewed(self):
        stage_grounded_price_leads(self.preview())
        lead = IngestionCandidate.objects.get()
        self.assertFalse(promote_approved_price_candidate(lead.pk))
        self.assertFalse(MarketPriceObservation.objects.exists())

    def test_approved_rights_permitted_promotes_only_pending_observation_once(self):
        lead = self._approved()
        self.assertTrue(promote_approved_price_candidate(lead.pk))
        self.assertFalse(promote_approved_price_candidate(lead.pk))
        self.assertEqual(MarketPriceObservation.objects.count(), 1)
        row = MarketPriceObservation.objects.get()
        self.assertEqual(row.verification_status, "pending")
        self.assertIsNone(row.reviewed_at)
        self.assertEqual(row.pta_verification, "reported")
        self.assertEqual(row.price_max_pkr, Decimal("70000"))
        self.assertEqual(row.listing_status, "unknown")
        self.assertEqual(IngestionCandidate.objects.get().status, "ingested")

    def test_cannot_change_approved_price_after_review(self):
        lead = self._approved()
        lead.payload["price_min_pkr"] = "10000"
        lead.save(update_fields=["payload"])
        self.assertFalse(promote_approved_price_candidate(lead.pk))
        self.assertFalse(MarketPriceObservation.objects.exists())

    def test_cannot_switch_variant_after_approval(self):
        lead = self._approved()
        lead.payload["variant_name"] = "16/512"
        lead.save(update_fields=["payload"])
        self.assertFalse(promote_approved_price_candidate(lead.pk))
        self.assertFalse(MarketPriceObservation.objects.exists())

    @override_settings(RESEARCH_JOB_QUEUE_ENABLED=True, GEMINI_WEB_RESEARCH_ENABLED=True, GEMINI_API_KEY="test-key")
    def test_worker_stages_only_then_completes(self):
        job = ResearchJob.objects.create(criteria={"city": "Lahore", "budget_pkr": "80000"})
        with patch("recommendations.tasks.research_with_gemini", return_value=self.preview()) as remote:
            run_research_job(str(job.pk))
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.counts["staged"], 1)
        self.assertFalse(MarketPriceObservation.objects.exists())
        self.assertEqual(remote.call_args.kwargs["structured"], True)
        self.assertEqual(remote.call_args.args[0]["catalog_variants"][0]["device_slug"], self.device.slug)

    @override_settings(RESEARCH_JOB_QUEUE_ENABLED=True, GEMINI_WEB_RESEARCH_ENABLED=True, GEMINI_API_KEY="test-key")
    def test_duplicate_worker_dispatch_does_not_stage_twice(self):
        job = ResearchJob.objects.create(criteria={"city": "Lahore"})
        with patch("recommendations.tasks.research_with_gemini", return_value=self.preview()) as remote:
            run_research_job(str(job.pk))
            run_research_job(str(job.pk))
        remote.assert_called_once()
        self.assertEqual(IngestionCandidate.objects.count(), 1)

    @override_settings(RESEARCH_JOB_QUEUE_ENABLED=True, GEMINI_WEB_RESEARCH_ENABLED=True, GEMINI_API_KEY="test-key")
    def test_provider_error_does_not_leak_secrets_or_stage(self):
        job = ResearchJob.objects.create(criteria={"city": "Lahore"})
        with patch("recommendations.tasks.research_with_gemini", side_effect=RuntimeError("test-key bearer secret")):
            run_research_job(str(job.pk))
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertNotIn("test-key", job.notice)
        self.assertEqual(IngestionCandidate.objects.count(), 0)

    @override_settings(RESEARCH_JOB_QUEUE_ENABLED=False, GEMINI_WEB_RESEARCH_ENABLED=True, GEMINI_API_KEY="test-key")
    def test_worker_fails_closed_when_queue_disabled(self):
        job = ResearchJob.objects.create(criteria={"city": "Lahore"})
        with patch("recommendations.tasks.research_with_gemini") as remote:
            run_research_job(str(job.pk))
        self.assertEqual(ResearchJob.objects.get(pk=job.pk).status, "failed")
        remote.assert_not_called()


@override_settings(RESEARCH_JOB_QUEUE_ENABLED=True, GEMINI_WEB_RESEARCH_ENABLED=True,
                   GEMINI_API_KEY="test-key")
class ResearchJobAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        throttle = patch("recommendations.views.ResearchJobCollectionView.throttle_classes", [])
        throttle.start()
        self.addCleanup(throttle.stop)
        detail = patch("recommendations.views.ResearchJobDetailView.throttle_classes", [])
        detail.start()
        self.addCleanup(detail.stop)
        User = get_user_model()
        self.staff = User.objects.create_user(username="reviewer", password="sample-local-password", is_staff=True)
        self.other = User.objects.create_user(username="other", password="sample-local-password", is_staff=True)
        self.normal = User.objects.create_user(username="visitor", password="sample-local-password")

    def test_anonymous_and_nonstaff_cannot_create_job(self):
        url = "/api/recommendations/research-jobs/"
        self.assertIn(self.client.post(url, {"message": "used gaming under 80k"}).status_code, (401, 403))
        self.client.force_authenticate(self.normal)
        self.assertEqual(self.client.post(url, {"message": "used gaming under 80k"}).status_code, 403)
        self.assertEqual(ResearchJob.objects.count(), 0)

    def test_staff_creates_bounded_job_and_receives_poll_url(self):
        self.client.force_authenticate(self.staff)
        with patch("recommendations.tasks.run_research_job.apply_async") as enqueue:
            response = self.client.post("/api/recommendations/research-jobs/",
                {"message": "Mujhe Lahore mein 80 hazar tak used PTA gaming phone", "session_id": "f98d15e2-ad78-4f12-9b0a-13ba6d246693"}, format="json")
        self.assertEqual(response.status_code, 202)
        enqueue.assert_called_once()
        job = ResearchJob.objects.get()
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.requested_by, self.staff)
        self.assertNotIn("message", job.criteria)
        self.assertNotIn("session_id", job.criteria)
        self.assertEqual(job.criteria["budget_pkr"], "80000")
        poll = self.client.get(response.data["poll_url"])
        self.assertEqual(poll.status_code, 200)
        self.assertEqual(poll.data["status"], "queued")

    def test_staff_cannot_read_other_staff_job(self):
        job = ResearchJob.objects.create(requested_by=self.staff, criteria={})
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f"/api/recommendations/research-jobs/{job.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/api/recommendations/research-jobs/").data["results"], [])

    def test_broker_error_returns_503_no_secrets(self):
        self.client.force_authenticate(self.staff)
        with patch("recommendations.tasks.run_research_job.apply_async", side_effect=RuntimeError("api-key secret")):
            result = self.client.post("/api/recommendations/research-jobs/", {"message": "used PTA gaming under 80k"})
        self.assertEqual(result.status_code, 503)
        self.assertNotIn("secret", str(result.data))
        self.assertEqual(ResearchJob.objects.get().status, "failed")

    @override_settings(RESEARCH_JOB_QUEUE_ENABLED=False)
    def test_disabled_queue_refuses_paid_job(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post("/api/recommendations/research-jobs/", {"message": "used phone"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(ResearchJob.objects.count(), 0)
