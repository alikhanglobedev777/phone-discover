"""Conservative, source-attributed PKR refresh for *existing* exact device variants.

No device/specification writes. No verified offers/PTA claims. No unlicensed sources.
Previously recorded observations are immutable; each accepted check appends a row.
"""

from datetime import timedelta
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from decimal import Decimal
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.text import slugify

from recommendations.provider_config import research_available
from recommendations.research_providers import research_catalog
from recommendations.catalog_research import source_url

from .models import DeviceVariant, MarketPriceObservation, PriceRefreshRun, PriceRefreshCheck, ResearchSource
from .web_import import _validate

log = logging.getLogger(__name__)
REFRESH_LOCK_ID = 7692308051235  # PostgreSQL session advisory lock, shared by CLI/admin jobs.
SUPPORTED_HOSTS = frozenset({"priceoye.pk", "whatmobile.com.pk"})
COUNTER_KEYS = ("variants_checked", "observations_added", "unchanged", "blocked_sources", "rejected", "research_failed")


def allowed_source_url(url):
    """A cited, normalized HTTPS *product page* from the two supported hosts."""
    canonical = source_url(url)
    if not canonical:
        return None
    host = (urlsplit(canonical).hostname or "").removeprefix("www.")
    if host not in SUPPORTED_HOSTS or len(urlsplit(canonical).path) < 4:
        return None
    return canonical


def valid_for_variant(phone, sources, variant):
    """Refuse uncertain identity/configuration rather than assigning a wrong price."""
    if not isinstance(phone, dict):
        raise ValueError("Invalid sourced phone")
    facts = _validate(phone, sources)
    if (slugify(facts["brand"]) != slugify(variant.device.brand.name)
            or slugify(facts["name"]) != slugify(variant.device.name)
            or facts["ram"] != variant.ram_gb or facts["storage"] != variant.storage_gb):
        raise ValueError("Product does not match existing exact RAM/storage variant")
    if facts["listing"] == MarketPriceObservation.ListingStatus.ENDED:
        raise ValueError("Ended or out-of-stock listings cannot establish a current retail price")
    if facts["condition"] != MarketPriceObservation.Condition.BOX_PACK:
        raise ValueError("Refresh only supports clearly described box-packed retail prices")
    if not allowed_source_url(facts["url"]):
        raise ValueError("Unapproved price source")
    return facts


def _research_variant(variant):
    criteria = {
        "brand": variant.device.brand.slug,
        "device_query": variant.device.name,
        "ram_min": variant.ram_gb,
        "storage_min": variant.storage_gb,
        "condition": "box_pack",
    }
    result = research_catalog(criteria)
    if result.get("status") != "grounded_preview":
        return [], False
    cited = {
        allowed_source_url(entry.get("url"))
        for entry in result.get("sources", [])
        if isinstance(entry, dict)
    } - {None}
    phones = result.get("document", {}).get("phones", [])
    if not isinstance(phones, list) or len(phones) > 4:
        return [], False
    facts = []
    for phone in phones:
        try:
            candidate = valid_for_variant(phone, cited, variant)
        except (ValueError, TypeError, KeyError, ValidationError):
            continue
        if candidate["url"] not in {item["url"] for item in facts}:
            facts.append(candidate)
    return facts, True


def _save_observation(variant, facts, *, now):
    """Insert-only. Existing human-verified prices and review decisions never change."""
    url = facts["url"]
    host = urlsplit(url).hostname.removeprefix("www.")
    with transaction.atomic():
        # Serialize writes for one variant from concurrent research processes.
        DeviceVariant.objects.select_for_update().get(pk=variant.pk)
        source, _ = ResearchSource.objects.get_or_create(
            url=url,
            defaults={
                "title": f"{variant.device.brand.name} {variant.device.name} retail price source"[:255],
                "publisher": host,
                "source_type": ResearchSource.SourceType.RETAILER,
                "reuse_status": ResearchSource.ReuseStatus.UNKNOWN,
                "reuse_notes": "Awaiting administrator's source-use assessment for automated price refresh.",
            },
        )
        # Never assume that discoverable web content may be automatically republished.
        if source.reuse_status != ResearchSource.ReuseStatus.PERMITTED or not source.reuse_notes.strip():
            return "blocked_sources"
        records = MarketPriceObservation.objects.filter(
            variant=variant, source=source, condition=MarketPriceObservation.Condition.BOX_PACK,
        )
        if records.filter(verification_status="rejected").exists():
            return "rejected"
        latest = records.order_by("-observed_at", "-pk").first()
        # Avoid near-duplicate records from repeated admin clicks.
        if (latest and latest.verification_status == "web_reported"
                and latest.observed_at > now - timedelta(hours=4)
                and latest.price_min_pkr == facts["minimum"]
                and latest.price_max_pkr == facts["maximum"]):
            return "unchanged"
        if latest:
            previous = (latest.price_min_pkr + latest.price_max_pkr) / 2
            incoming = (facts["minimum"] + facts["maximum"]) / 2
            limit = Decimal(str(max(0, min(1, settings.PRICE_REFRESH_PRICE_CHANGE_LIMIT))))
            if previous > 0 and abs(incoming - previous) / previous > limit:
                log.warning("Price refresh rejected suspicious change for variant_id=%s source_id=%s", variant.pk, source.pk)
                return "rejected"
        observation = MarketPriceObservation(
            variant=variant,
            source=source,
            condition=MarketPriceObservation.Condition.BOX_PACK,
            pta_status=facts["pta"],
            pta_verification="unknown" if facts["pta"] == "unknown" else "reported",
            city=facts["city"],
            seller_name="PriceOye" if host == "priceoye.pk" else "WhatMobile",
            listing_url=url,
            listing_status=facts["listing"],
            price_min_pkr=facts["minimum"],
            price_max_pkr=facts["maximum"],
            observed_at=now,
            verification_status="web_reported",
            notes=("Scheduled/admin research observation from cited product-page evidence. "
                   "Asking price only; unreviewed source-reported amount, not confirmed stock "
                   "or independently validated PTA approval."),
        )
        observation.full_clean()
        observation.save(force_insert=True)
        source.last_checked_at = now
        source.save(update_fields=["last_checked_at", "updated_at"])
        return "observations_added"


def refresh_run(run, *, limit=None):
    """Run one bounded cycle, with a database-wide mutual exclusion lock."""
    counts = dict.fromkeys(COUNTER_KEYS, 0)
    if run.status != PriceRefreshRun.Status.QUEUED:
        return counts
    if not settings.PRICE_REFRESH_ENABLED or not research_available():
        PriceRefreshRun.objects.filter(pk=run.pk, status="queued").update(
            status="failed", notice="Refresh disabled or web research not configured.", finished_at=timezone.now())
        return counts
    # Only PostgreSQL is supported by this backend's production configuration.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [REFRESH_LOCK_ID])
        locked = cursor.fetchone()[0]
    if not locked:
        PriceRefreshRun.objects.filter(pk=run.pk, status="queued").update(
            status="failed", notice="Another price refresh is already running.", finished_at=timezone.now())
        return counts
    try:
        started = timezone.now()
        claimed = PriceRefreshRun.objects.filter(pk=run.pk, status="queued").update(
            status="running", started_at=started, notice="Checking exact retail variants.")
        if not claimed:
            return counts
        cap = min(max(1, int(limit or settings.PRICE_REFRESH_MAX_VARIANTS)), 250)
        cutoff = started - timedelta(hours=48)
        # Track attempts separately from successful observations. A blocked or failed
        # source must not cause the same 40 phones to starve the rest of the catalog.
        variants = (DeviceVariant.objects.filter(
            device__is_published=True, device__status="available", device__brand__is_active=True,
        ).select_related("device", "device__brand")
        .order_by(F("price_refresh_check__last_attempted_at").asc(nulls_first=True), "pk"))
        if not run.force:
            variants = variants.filter(
                Q(price_refresh_check__isnull=True) |
                Q(price_refresh_check__last_attempted_at__lte=cutoff)
            )
        try:
            for variant in variants[:cap].iterator(chunk_size=20):
                counts["variants_checked"] += 1
                outcome = "unavailable"
                try:
                    facts_list, ok = _research_variant(variant)
                    if not ok:
                        counts["research_failed"] += 1
                    elif not facts_list:
                        counts["rejected"] += 1
                        outcome = "no_exact_source_match"
                    for facts in facts_list:
                        result = _save_observation(variant, facts, now=timezone.now())
                        counts[result] += 1
                        outcome = result
                except (ValueError, TypeError, ValidationError):
                    counts["rejected"] += 1
                    outcome = "invalid_evidence"
                except Exception:
                    log.exception("Price refresh failed for variant_id=%s", variant.pk)
                    counts["research_failed"] += 1
                    outcome = "error"
                # Attempt cursor records every attempt, not just successful price saves.
                PriceRefreshCheck.objects.update_or_create(
                    variant=variant, defaults={"last_attempted_at": timezone.now(), "last_result": outcome}
                )
                # Visible progress throughout long provider calls; never store model text.
                PriceRefreshRun.objects.filter(pk=run.pk, status="running").update(counts=counts)
                # Modest pacing for provider and source-site rate limits.
                time.sleep(min(10.0, max(0.0, settings.PRICE_REFRESH_DELAY_SECONDS)))
            PriceRefreshRun.objects.filter(pk=run.pk, status="running").update(
                status="completed", counts=counts, finished_at=timezone.now(),
                notice="Complete. Prices are source-reported, not independently verified.")
        except Exception:
            log.exception("Price refresh run failed")
            PriceRefreshRun.objects.filter(pk=run.pk, status="running").update(
                status="failed", counts=counts, finished_at=timezone.now(),
                notice="Refresh stopped due to an internal error; check server logs.")
        return counts
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [REFRESH_LOCK_ID])


def launch_async(run):
    """Local Windows admin convenience only; scheduled task is the durable timer."""
    backend = Path(settings.BASE_DIR)
    args = [sys.executable, str(backend / "manage.py"), "refresh_phone_prices", "--run-id", str(run.pk)]
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if os.name == "nt":
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    try:
        subprocess.Popen(
            args, cwd=str(backend), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True, creationflags=flags,
        )
    except OSError:
        PriceRefreshRun.objects.filter(pk=run.pk).update(
            status="failed", notice="Could not start background process. Run the Django command manually.",
            finished_at=timezone.now())
        return False
    return True
