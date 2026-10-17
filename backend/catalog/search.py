"""Read-only, evidence-gated Pakistani catalog search for future AI retrieval.

Each candidate is an exact DeviceVariant and (where price is requested) one
eligible MarketPriceObservation. Unlike chained device-level joins, RAM,
storage, scores and prices cannot come from different variants. Nothing in
this service searches the web or modifies catalog data.
"""

from datetime import date
from decimal import Decimal

from django.db.models import Exists, OuterRef, Prefetch, Q, Value
from django.db.models.functions import Concat, Lower, Trim
from django.urls import reverse

from .models import DeviceVariant, MarketPriceObservation, ResearchSource
from .pricing import PRICE_GUIDE_DISCLAIMER, budget_fit, eligible_price_observations


def _matching_prices(criteria, *, as_of=None):
    qs = eligible_price_observations(as_of=as_of)
    for field in ("condition", "grade", "pta_status", "pta_verification"):
        if criteria.get(field):
            qs = qs.filter(**{field: criteria[field]})
    if criteria.get("city"):
        qs = qs.annotate(_search_city=Lower(Trim("city"))).filter(
            _search_city=criteria["city"].casefold()
        )
    budget = criteria.get("budget_pkr")
    if budget is not None:
        field = (
            "price_max_pkr__lte"
            if criteria.get("budget_mode", "strict") == "strict"
            else "price_min_pkr__lte"
        )
        qs = qs.filter(**{field: budget})
    return qs


def _verified_observations(observations):
    """Defence in depth, including whitespace-only evidence and duplicate URLs."""
    seen_urls = set()
    result = []
    for obs in sorted(observations, key=lambda p: (p.observed_at, p.pk), reverse=True):
        if obs.source_id:
            if (obs.source.reuse_status != ResearchSource.ReuseStatus.PERMITTED
                    or not obs.source.reuse_notes.strip()):
                continue
        elif not obs.notes.strip():
            continue
        url = obs.listing_url.strip()
        if url:
            if url in seen_urls:
                continue
            seen_urls.add(url)
        result.append(obs)
    return result


def _price_payload(price, budget_pkr=None):
    if price is None:
        return None
    return {
        "currency": "PKR",
        "condition": price.condition,
        "grade": price.grade,
        "pta_status": price.pta_status,
        "pta_verification": price.pta_verification,
        "city": price.city.strip(),
        "observed_min_pkr": str(price.price_min_pkr),
        "observed_max_pkr": str(price.price_max_pkr),
        "observed_at": price.observed_at.isoformat(),
        "source_url": price.source.url if price.source_id else None,
        "evidence_type": "linked_source" if price.source_id else "admin_documented",
        "availability": "not_confirmed",
        "budget_fit": budget_fit(price.price_min_pkr, price.price_max_pkr, budget_pkr),
    }


def _rank_key(item, *, sort, query):
    variant, price = item
    device = variant.device
    high = price.price_max_pkr if price is not None else Decimal("Infinity")
    low = price.price_min_pkr if price is not None else Decimal("Infinity")
    tie = (high, low, device.name.casefold(), variant.pk)
    if sort == "camera":
        return (-variant.camera_score, *tie)
    if sort == "gaming":
        return (-variant.gaming_score, *tie)
    if sort == "battery":
        return (-variant.battery_score, *tie)
    if sort == "newest":
        # date.min is legitimate: unknown release dates sort after known dates.
        return (-(device.release_date or date.min).toordinal(), *tie)
    if sort == "name":
        return (device.brand.name.casefold(), device.name.casefold(), *tie)
    if sort == "relevance" and query:
        full = f"{device.brand.name} {device.name}".casefold()
        phrase = query.casefold()
        match = 0 if full == phrase else 1 if full.startswith(phrase) else 2
        return (match, *tie)
    return tie


def search_local_catalog(criteria, *, as_of=None):
    """Return one best matching variant per published device, with evidence.

    Pagination is after deduplication so one phone never fills multiple cards.
    A price requirement is on by default; turn it off for specs-only lookup.
    This is a read-only synchronous catalog lookup, not a research agent.
    """
    require_price = criteria.get("require_price", True)
    query = (criteria.get("q") or "").strip()
    variants = DeviceVariant.objects.filter(device__is_published=True).select_related(
        "device", "device__brand"
    )
    if criteria.get("brand"):
        variants = variants.filter(device__brand__slug__iexact=criteria["brand"])
    if criteria.get("os"):
        variants = variants.filter(device__operating_system__icontains=criteria["os"])
    if criteria.get("status"):
        variants = variants.filter(device__status=criteria["status"])
    if query:
        variants = variants.annotate(
            search_full_name=Concat("device__brand__name", Value(" "), "device__name")
        ).filter(
            Q(device__name__icontains=query)
            | Q(device__brand__name__icontains=query)
            | Q(search_full_name__icontains=query)
            | Q(device__summary__icontains=query)
            | Q(chipset__icontains=query)
        )

    for field, lookup in (
        ("ram_min", "ram_gb__gte"),
        ("storage_min", "storage_gb__gte"),
        ("camera_min", "camera_score__gte"),
        ("gaming_min", "gaming_score__gte"),
        ("battery_min", "battery_score__gte"),
    ):
        if criteria.get(field) is not None:
            variants = variants.filter(**{lookup: criteria[field]})

    matched_prices = _matching_prices(criteria, as_of=as_of)
    if require_price:
        # Correlation is to ONE variant. Every observation criterion must
        # hold on ONE price observation, never on separate related rows.
        variants = variants.filter(
            Exists(matched_prices.filter(variant_id=OuterRef("pk")))
        )
    variants = variants.prefetch_related(
        Prefetch(
            "pk_market_prices",
            queryset=matched_prices.select_related("source").order_by("-observed_at", "-id"),
            to_attr="search_price_observations",
        )
    )

    candidates = []
    for variant in variants:
        eligible = _verified_observations(variant.search_price_observations)
        if criteria.get("city"):
            # Casefold and whitespace validation supplement DB's ILIKE filter.
            eligible = [
                item for item in eligible
                if item.city.strip().casefold() == criteria["city"].casefold()
            ]
        best_price = min(
            eligible,
            key=lambda p: (p.price_max_pkr, p.price_min_pkr, -p.observed_at.timestamp(), p.pk),
            default=None,
        )
        if require_price and best_price is None:
            continue
        candidates.append((variant, best_price))

    candidates.sort(key=lambda item: _rank_key(item, sort=criteria.get("sort", "relevance"), query=query))
    by_device = []
    seen_devices = set()
    for variant, price in candidates:
        if variant.device_id in seen_devices:
            continue
        seen_devices.add(variant.device_id)
        by_device.append((variant, price))

    count = len(by_device)
    page = criteria.get("page", 1)
    page_size = criteria.get("page_size", 20)
    start = (page - 1) * page_size
    results = []
    for variant, price in by_device[start:start + page_size]:
        device = variant.device
        results.append({
            "id": device.pk,
            "slug": device.slug,
            "name": device.name,
            "brand": {"name": device.brand.name, "slug": device.brand.slug},
            "status": device.status,
            "summary": device.summary,
            "primary_image_url": device.primary_image_url,
            "detail_api_url": reverse("device-detail", kwargs={"slug": device.slug}),
            "variant": {
                "id": variant.pk,
                "name": variant.name,
                "ram_gb": variant.ram_gb,
                "storage_gb": variant.storage_gb,
                "chipset": variant.chipset,
                "camera_score": str(variant.camera_score),
                "gaming_score": str(variant.gaming_score),
                "battery_score": str(variant.battery_score),
            },
            "price_observation": _price_payload(price, criteria.get("budget_pkr")),
        })
    return {
        "count": count,
        "page": page,
        "page_size": page_size,
        "has_more": start + page_size < count,
        "needs_research": count == 0,
        "research_reason": "no_matching_local_evidence" if count == 0 else None,
        "results": results,
        "price_disclaimer": PRICE_GUIDE_DISCLAIMER,
    }
