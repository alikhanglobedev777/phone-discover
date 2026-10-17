"""Evidence-gated Pakistani smartphone price observations (not sales offers).

The public guide contains *samples*, not quotes, stock guarantees, or a PTA
certificate. This service is reusable by the later recommendation engine.
Never use legacy MarketOffer here: it has neither condition nor PTA evidence.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from statistics import median

from django.db.models import Q
from django.utils import timezone

from .models import MarketPriceObservation, ResearchSource, ReviewStatus


# A short freshness window is particularly important for second-hand listings.
FRESHNESS_DAYS = {
    MarketPriceObservation.Condition.BOX_PACK: 30,
    MarketPriceObservation.Condition.OPEN_BOX: 21,
    MarketPriceObservation.Condition.USED: 14,
    MarketPriceObservation.Condition.REFURBISHED: 21,
}
PKR_QUANTUM = Decimal("0.01")
PRICE_GUIDE_DISCLAIMER = (
    "Observed Pakistani asking-price samples, not guaranteed market values or "
    "live inventory. Condition, storage, city and PTA classification are kept "
    "separate. Seller-reported PTA status is not independent IMEI verification; "
    "verify each handset yourself before buying."
)


def budget_fit(observed_min_pkr, observed_max_pkr, budget_pkr):
    """Conservative three-state signal; 'possible' is not a guaranteed deal."""
    if budget_pkr is None:
        return None
    budget = Decimal(str(budget_pkr))
    if budget < 0 or not budget.is_finite():
        raise ValueError("budget_pkr must be a non-negative finite PKR amount")
    low, high = Decimal(str(observed_min_pkr)), Decimal(str(observed_max_pkr))
    if high <= budget:
        return "within_observed_range"
    if low <= budget:
        return "possibly_within_budget"
    return "above_budget"


def _price_string(value):
    return str(Decimal(value).quantize(PKR_QUANTUM, rounding=ROUND_HALF_UP))


def price_summaries_for_device(
    device_id,
    *,
    variant_id=None,
    condition=None,
    grade=None,
    pta_status=None,
    pta_verification=None,
    city=None,
    budget_pkr=None,
    as_of=None,
):
    """Return comparable, de-duplicated *public-safe* observation groups.

    A verified observation can be used if its source explicitly allows reuse
    with documented permission, or a human has recorded review evidence in
    notes without a source record.
    Stale, future, ended, pending and rejected observations never enter groups.
    The grouping keys prevent accidental cross-condition, cross-city, or
    reported-vs-checked PTA comparisons. Prices remain tied to exact variants.
    """
    now = as_of if as_of is not None else timezone.now()
    if timezone.is_naive(now):
        raise ValueError("as_of must be timezone-aware")
    normalized_city = (city or "").strip().casefold()
    earliest = now - timedelta(days=max(FRESHNESS_DAYS.values()))

    qs = (
        MarketPriceObservation.objects.filter(
            variant__device_id=device_id,
            variant__device__is_published=True,
            verification_status=ReviewStatus.VERIFIED,
            reviewed_at__isnull=False,
            observed_at__gte=earliest,
            observed_at__lte=now,
        )
        .exclude(listing_status=MarketPriceObservation.ListingStatus.ENDED)
        .filter(
            Q(source__isnull=True)
            | (Q(source__reuse_status=ResearchSource.ReuseStatus.PERMITTED)
               & ~Q(source__reuse_notes=""))
        )
        .select_related("source")
        .order_by("-observed_at", "-id")
    )
    if variant_id is not None:
        qs = qs.filter(variant_id=variant_id)
    if condition:
        qs = qs.filter(condition=condition)
    if grade:
        qs = qs.filter(grade=grade)
    if pta_status:
        qs = qs.filter(pta_status=pta_status)
    if pta_verification:
        qs = qs.filter(pta_verification=pta_verification)

    groups = defaultdict(list)
    seen_listings = set()
    for observation in qs:
        if observation.observed_at < now - timedelta(days=FRESHNESS_DAYS[observation.condition]):
            continue
        if observation.source_id is None and not observation.notes.strip():
            continue
        clean_city = observation.city.strip()
        if normalized_city and clean_city.casefold() != normalized_city:
            continue
        group_key = (
            observation.variant_id,
            observation.condition,
            observation.grade,
            observation.pta_status,
            observation.pta_verification,
            clean_city.casefold(),
        )
        # A refreshed listing is one observation, not two independent samples.
        # No URL means we cannot safely infer whether two records are duplicates.
        listing_url = observation.listing_url.strip()
        if listing_url:
            listing_key = (group_key, listing_url)
            if listing_key in seen_listings:
                continue
            seen_listings.add(listing_key)
        groups[group_key].append(observation)

    summaries = []
    for key, observations in groups.items():
        variant, condition_value, grade_value, pta, pta_checked, normalized_group_city = key
        observed_low = min(o.price_min_pkr for o in observations)
        observed_high = max(o.price_max_pkr for o in observations)
        midpoints = [(o.price_min_pkr + o.price_max_pkr) / Decimal("2") for o in observations]
        latest = max(o.observed_at for o in observations)
        # Give an observation median, not an unqualified model-wide "market price".
        sources = {}
        for o in observations:
            if o.source_id is not None:
                sources[o.source_id] = o.source
        source_links = [
            {"title": src.title, "url": src.url}
            for _, src in sorted(sources.items())[:5]
        ]
        summaries.append(
            {
                "variant_id": variant,
                "condition": condition_value,
                "grade": grade_value,
                "pta_status": pta,
                "pta_verification": pta_checked,
                "city": observations[0].city.strip(),
                "currency": "PKR",
                "observation_count": len(observations),
                "source_count": len(sources),
                "evidence_type": "linked_sources" if sources else "admin_documented",
                "observed_min_pkr": _price_string(observed_low),
                "observed_max_pkr": _price_string(observed_high),
                "median_observed_midpoint_pkr": _price_string(median(midpoints)),
                "last_observed_at": latest.isoformat(),
                "freshness_days": FRESHNESS_DAYS[condition_value],
                "active_when_checked_count": sum(
                    o.listing_status == MarketPriceObservation.ListingStatus.ACTIVE
                    for o in observations
                ),
                "availability": "not_confirmed",
                "sample_size": "single_observation" if len(observations) == 1 else "multiple_observations",
                "budget_fit": budget_fit(observed_low, observed_high, budget_pkr),
                "sources": source_links,
            }
        )
    return sorted(
        summaries,
        key=lambda item: (
            item["variant_id"], item["condition"], item["grade"],
            item["pta_status"], item["pta_verification"], item["city"].casefold(),
        ),
    )
