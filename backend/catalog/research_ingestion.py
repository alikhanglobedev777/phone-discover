"""Stage *untrusted* grounded Gemini price leads; promote only after human review.

No AI-sourced content becomes verified or public in this module. Supported
candidates match an existing exact device/variant; no new products are created.
"""

import hashlib
import json
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    DeviceVariant, IngestionCandidate, MarketPriceObservation, ResearchSource,
)
from recommendations.gemini_research import _safe_link


MAX_PROPOSALS = 8
ALLOWED_CONDITIONS = {x for x, _ in MarketPriceObservation.Condition.choices}
ALLOWED_PTA = {x for x, _ in MarketPriceObservation.PTAStatus.choices}
ALLOWED_GRADES = {x for x, _ in MarketPriceObservation.Grade.choices}


def _decimal_price(value):
    # Reject booleans, floats, exponent notation and unbounded values.
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("Invalid price")
    raw = str(value)
    if not raw or len(raw) > 12 or not raw.replace(".", "", 1).isdigit():
        raise ValueError("Invalid price")
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("Invalid price") from exc
    if result <= 0 or result > 20000000 or result.as_tuple().exponent < -2:
        raise ValueError("Price out of bounds")
    return result


def _validated_lead(lead, trusted_sources):
    if not isinstance(lead, dict) or lead.get("type") != "price":
        raise ValueError("Unsupported proposal")
    url = lead.get("source_url")
    if not isinstance(url, str) or url not in trusted_sources or not _safe_link(url):
        raise ValueError("Source URL is not in grounding metadata")
    if not isinstance(lead.get("device_slug"), str) or len(lead["device_slug"]) > 220:
        raise ValueError("Invalid device slug")
    if not isinstance(lead.get("variant_name"), str) or len(lead["variant_name"]) > 160:
        raise ValueError("Invalid variant")
    variants = DeviceVariant.objects.filter(
        device__slug=lead["device_slug"], name__iexact=lead["variant_name"]
    )[:2]
    matches = list(variants)
    if len(matches) != 1:
        raise ValueError("Exact existing variant required")
    condition = lead.get("condition")
    pta = lead.get("pta_status")
    grade = lead.get("grade", "")
    if condition not in ALLOWED_CONDITIONS or pta not in ALLOWED_PTA:
        raise ValueError("Invalid condition or PTA classification")
    if grade not in ALLOWED_GRADES | {""} or (grade and condition not in ("used", "refurbished")):
        raise ValueError("Invalid condition grade")
    city = lead.get("city", "")
    if not isinstance(city, str) or len(city) > 100 or any(ord(c) < 32 for c in city):
        raise ValueError("Invalid city")
    minimum = _decimal_price(lead.get("price_min_pkr"))
    maximum = _decimal_price(lead.get("price_max_pkr"))
    if maximum < minimum:
        raise ValueError("Reversed price range")
    # Gemini cannot assert an independently verified handset PTA check.
    payload = {
        "device_slug": matches[0].device.slug if matches[0].device_id else lead["device_slug"],
        "variant_name": matches[0].name,
        "condition": condition,
        "grade": grade,
        "pta_status": pta,
        "pta_verification": "unknown" if pta == "unknown" else "reported",
        "city": city.strip(),
        "price_min_pkr": str(minimum),
        "price_max_pkr": str(maximum),
        "source_url": url,
    }
    return matches[0], payload


def stage_grounded_price_leads(research):
    """Only a *grounded_preview* with citations may create PENDING candidates.

    Text that is not a strict JSON object is ignored, not scraped heuristically.
    Sources are created with `reuse_status=unknown` by default, NEVER permitted.
    """
    stats = {"staged": 0, "duplicates": 0, "rejected": 0}
    if not isinstance(research, dict) or research.get("status") != "grounded_preview":
        return stats
    sources = research.get("sources")
    summary = research.get("summary")
    if not isinstance(sources, list) or not isinstance(summary, str) or len(summary) > 9000:
        return stats
    trusted = {
        item["url"]: str(item.get("title") or "Research lead")[:255]
        for item in sources if isinstance(item, dict) and _safe_link(item.get("url"))
    }
    if not trusted:
        return stats
    try:
        document = json.loads(summary)
    except (TypeError, ValueError):
        return stats
    if not isinstance(document, dict) or not isinstance(document.get("proposals"), list):
        return stats
    leads = document["proposals"]
    if len(leads) > MAX_PROPOSALS:
        return stats  # Fail closed rather than taking an attacker-selected prefix.
    for lead in leads:
        try:
            variant, payload = _validated_lead(lead, trusted)
        except (ValueError, TypeError, KeyError):
            stats["rejected"] += 1
            continue
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(("price:" + encoded).encode("utf-8")).hexdigest()
        with transaction.atomic():
            url = payload["source_url"]
            source, _ = ResearchSource.objects.get_or_create(
                url=url, defaults={"title": trusted[url], "reuse_status": ResearchSource.ReuseStatus.UNKNOWN}
            )
            _, created = IngestionCandidate.objects.get_or_create(
                fingerprint=fingerprint,
                defaults={"candidate_type": IngestionCandidate.CandidateType.PRICE,
                          "matched_device": variant.device, "source": source, "payload": payload},
            )
        stats["staged" if created else "duplicates"] += 1
    return stats


def promote_approved_price_candidate(candidate_id):
    """Admin-only path: reviewed + rights-permitted -> PENDING observation.

    Idempotent by candidate status under row lock. This never sets verification
    status to verified, never changes a Device and never sets PTA 'checked'.
    """
    with transaction.atomic():
        # Lock only the candidate row. matched_device is nullable, so locking
        # the joined tables would make PostgreSQL reject the LEFT JOIN.
        candidate = (IngestionCandidate.objects.select_for_update(of=("self",))
                     .select_related("source", "matched_device").get(pk=candidate_id))
        if candidate.status != IngestionCandidate.Status.APPROVED or not candidate.reviewed_at:
            return False
        if candidate.candidate_type != IngestionCandidate.CandidateType.PRICE:
            return False
        if candidate.source.reuse_status != ResearchSource.ReuseStatus.PERMITTED:
            return False
        try:
            # Staging deliberately strips the untrusted proposal "type" marker.
            # Restore it only for revalidation; fingerprint the same stored facts.
            variant, clean = _validated_lead(
                {**candidate.payload, "type": "price"},
                {candidate.source.url: candidate.source.title},
            )
        except (ValueError, KeyError, TypeError):
            return False
        canonical = json.dumps(clean, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(("price:" + canonical).encode("utf-8")).hexdigest()
        if (expected != candidate.fingerprint or variant.device_id != candidate.matched_device_id or
                clean["source_url"] != candidate.source.url):
            return False
        observation = MarketPriceObservation(
            variant=variant, source=candidate.source, condition=clean["condition"],
            grade=clean["grade"], pta_status=clean["pta_status"],
            pta_verification=clean["pta_verification"], city=clean["city"],
            price_min_pkr=Decimal(clean["price_min_pkr"]),
            price_max_pkr=Decimal(clean["price_max_pkr"]),
            listing_url=clean["source_url"],
            listing_status=MarketPriceObservation.ListingStatus.UNKNOWN,
            observed_at=timezone.now(),
            verification_status="pending", reviewed_at=None,
            notes="AI-assisted research lead. Admin must independently verify price, freshness and PTA evidence.",
        )
        try:
            observation.full_clean()
        except ValidationError:
            return False
        observation.save()
        candidate.status = IngestionCandidate.Status.INGESTED
        candidate.save(update_fields=["status", "updated_at"])
    return True
