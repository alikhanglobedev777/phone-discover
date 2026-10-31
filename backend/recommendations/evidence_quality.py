"""Evidence provenance and strictly descriptive hardware facts.

A saved spec is not independently verified. Manufacturer URLs are links to a
manufacturer, NOT automatically evidence for each specification. Editorial
scores without linked review evidence remain editorial and non-benchmark.
Never infer photo quality from megapixels or battery life from mAh.
"""
from datetime import timedelta
from urllib.parse import urlsplit
import ipaddress

from django.db.models import Prefetch
from django.utils import timezone

from catalog.models import DeviceClaim, ResearchSource, ReviewStatus

SOURCE_FRESH_DAYS = 365
FIELD_LABELS = (
    ("battery_mah", "Battery capacity", "mAh", "Capacity alone does not prove battery life"),
    ("display_refresh_hz", "Display refresh rate", "Hz", "Refresh rate alone does not prove gaming performance"),
    ("ram_gb", "RAM", "GB", "Memory amount is not a speed benchmark"),
    ("storage_gb", "Storage", "GB", "Capacity is not storage speed"),
)


def public_source_url(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        u = urlsplit(value)
        host = u.hostname or ""
        if u.scheme != "https" or not host or u.username or u.password:
            return None
        if host.casefold() == "localhost" or "." not in host or host.endswith((".local", ".internal")):
            return None
        try:
            ip = ipaddress.ip_address(host)
            if not ip.is_global:
                return None
        except ValueError:
            pass
        return value
    except ValueError:
        return None


def reviewed_claim_queryset():
    return DeviceClaim.objects.filter(
        status=ReviewStatus.VERIFIED,
        reviewed_at__isnull=False,
        source__reuse_status=ResearchSource.ReuseStatus.PERMITTED,
    ).select_related("source")


def evidence_prefetch():
    return Prefetch("research_claims", queryset=reviewed_claim_queryset(), to_attr="reviewed_public_claims")


def public_evidence(device):
    claims = getattr(device, "reviewed_public_claims", None)
    if claims is None:
        claims = list(reviewed_claim_queryset().filter(device=device)[:40])
    today = timezone.now()
    valid = []
    for claim in claims[:40]:
        url = public_source_url(claim.source.url)
        if url:
            checked_at = claim.source.last_checked_at or claim.reviewed_at
            valid.append({
                "label": claim.source.title[:150], "url": url,
                "publisher": claim.source.publisher[:100],
                "field": claim.field_path[:150],
                "reviewed_at": claim.reviewed_at.isoformat(),
                "source_checked_at": checked_at.isoformat() if checked_at else None,
                "is_recent": bool(checked_at and checked_at >= today - timedelta(days=SOURCE_FRESH_DAYS)),
                "kind": "reviewed_claim",
            })
    # Deduplicate links but keep distinct reviewed claim field names as provenance.
    official = public_source_url(device.official_url)
    if official:
        valid.append({
            "label": "Manufacturer website (not independently verified)",
            "url": official, "publisher": device.brand.name,
            "field": None, "reviewed_at": None, "source_checked_at": None,
            "is_recent": False, "kind": "manufacturer_link",
        })
    vetted = [x for x in valid if x["kind"] == "reviewed_claim"]
    recent = [x for x in vetted if x["is_recent"]]
    verified = device.last_verified_at
    fresh_record = bool(verified and verified >= today - timedelta(days=SOURCE_FRESH_DAYS))
    if recent:
        tier = "reviewed_recent"
    elif vetted:
        tier = "reviewed_outdated"
    elif fresh_record:
        tier = "catalog_dated_no_source"
    else:
        tier = "catalog_unverified"
    return {
        "tier": tier,
        "label": {
            "reviewed_recent": "Recent reviewed source",
            "reviewed_outdated": "Reviewed source may be outdated",
            "catalog_dated_no_source": "Catalog date recorded; independent source unavailable",
            "catalog_unverified": "Catalog specs not independently verified",
        }[tier],
        "last_verified_at": verified.isoformat() if verified else None,
        "recent_reviewed_claims": len(recent),
        "reviewed_claims": len(vetted),
        "source_links": valid[:6],
        "caution": "Saved specs are not performance tests. A manufacturer link alone is not verification.",
    }


def descriptive_facts(variant):
    if variant is None:
        return []
    rows = []
    for field, name, unit, caution in FIELD_LABELS:
        value = getattr(variant, field, None)
        if value is not None and value > 0:
            rows.append({
                "field": field, "label": name, "value": value,
                "formatted": f"{value} {unit}", "unit": unit, "caution": caution,
            })
    if variant.chipset:
        rows.append({
            "field": "chipset", "label": "Chipset", "value": variant.chipset[:160],
            "formatted": variant.chipset[:160], "unit": "", "caution": "No chipset performance benchmark supplied",
        })
    return rows


def factual_comparison(first_variant, second_variant):
    """Higher numeric hardware property is not an overall phone winner."""
    left = {x["field"]: x for x in descriptive_facts(first_variant)}
    right = {x["field"]: x for x in descriptive_facts(second_variant)}
    rows = []
    for field in (*[x[0] for x in FIELD_LABELS], "chipset"):
        a, b = left.get(field), right.get(field)
        if a is None and b is None:
            continue
        rows.append({
            "field": field, "label": (a or b)["label"],
            "first": a["formatted"] if a else None,
            "second": b["formatted"] if b else None,
            "higher_spec_slug": None,  # Descriptive, never a performance verdict.
            "note": (a or b)["caution"],
        })
    return rows
