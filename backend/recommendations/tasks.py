"""Idempotent Celery job execution; no auto-publication or auto-approval."""
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import DeviceVariant
from catalog.research_ingestion import stage_grounded_price_leads
from .research_providers import research_preview as research_with_gemini
from .provider_config import research_available
from .models import ResearchJob


@shared_task(name="phone_discover.run_research_job", ignore_result=True)
def run_research_job(job_id):
    # Atomic state transition prevents duplicate dispatch from running twice.
    with transaction.atomic():
        job = ResearchJob.objects.select_for_update().filter(pk=job_id).first()
        if job is None or job.status != ResearchJob.Status.QUEUED:
            return
        if not (settings.RESEARCH_JOB_QUEUE_ENABLED and research_available()):
            job.status = ResearchJob.Status.FAILED
            job.notice = "Research integration is disabled."
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "notice", "finished_at"])
            return
        job.status = ResearchJob.Status.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])

    try:
        criteria = dict(job.criteria)
        # Grounding can propose prices for exact known variants only; do not
        # expose customer messages, session IDs or unbounded device data.
        filters = {"device__is_published": True}
        if criteria.get("brand"):
            filters["device__brand__slug"] = criteria["brand"]
        available = DeviceVariant.objects.filter(**filters).select_related("device").order_by("id")[:24]
        criteria["catalog_variants"] = [
            {"device_slug": v.device.slug, "variant_name": v.name,
             "ram_gb": v.ram_gb, "storage_gb": v.storage_gb}
            for v in available
        ]
        response = research_with_gemini(criteria, structured=True)
        if response.get("status") == "grounded_preview":
            counts = stage_grounded_price_leads(response)
            notice = "Grounded leads staged for human review; nothing is verified or published."
        else:
            counts = {"staged": 0, "duplicates": 0, "rejected": 0}
            notice = "Grounded research unavailable; no records staged."
        result = ResearchJob.Status.COMPLETED if response.get("status") == "grounded_preview" else ResearchJob.Status.FAILED
    except Exception:
        # Don't put exception messages in DB; provider errors can include secrets.
        counts = {"staged": 0, "duplicates": 0, "rejected": 0}
        notice = "Research processing failed; no verified records created."
        result = ResearchJob.Status.FAILED

    ResearchJob.objects.filter(pk=job_id, status=ResearchJob.Status.RUNNING).update(
        counts=counts, notice=notice, status=result, finished_at=timezone.now()
    )
