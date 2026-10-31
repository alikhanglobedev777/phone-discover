"""Catalog-grounded phone name resolution, specs discovery and comparisons.

Only published local models are returned. Editorial scores are not benchmarks;
unpriced results must NEVER claim a budget, condition, PTA or city match.
"""
import re

from catalog.models import Device, DeviceVariant
from .model_identity import matches_phone_model

MAX_DISCOVERY_VARIANTS = 750
QUALITY_DIMENSIONS = ("camera", "gaming", "battery")


def _alias_patterns(brand, name):
    """Exact token-boundary aliases. Longer suffixes (Ultra, Pro, 5G) win."""
    brand = brand.strip()
    name = name.strip()
    aliases = {name, f"{brand} {name}"}
    if brand.casefold() == "samsung" and name.casefold().startswith("galaxy "):
        stem = name[7:]
        aliases.update((f"Samsung {stem}", stem))
        # Don't turn an ambiguous number alone into a Galaxy model.
        if re.fullmatch(r"S\d{2} (?:Ultra|Plus|FE)(?: 5G)?", stem, flags=re.I):
            aliases.add(stem.replace("S", "S ", 1))
    if brand.casefold() == "google" and name.casefold().startswith("pixel "):
        aliases.add(f"Google {name}")
    normalized = []
    for alias in aliases:
        # Treat spaces and hyphens interchangeably, but never accept a partial
        # model token. e.g. S26 cannot match S26 Ultra as a final result.
        words = re.findall(r"[a-z0-9]+", alias.casefold())
        if words:
            normalized.append((len(words), re.compile(
                r"(?<![a-z0-9])" + r"[\s-]+".join(map(re.escape, words)) + r"(?![a-z0-9])",
                flags=re.I,
            )))
    return normalized


def catalog_mentions(message, *, max_matches=3):
    """Find models actually present in the DB, preferring full-name spans.

    A phone's alias cannot consume part of another recognized phone name.
    This works for any catalog brand, without appending a new regex per model.
    """
    if not message or not re.search(r"\d", message):
        return []
    matches = []
    qs = (Device.objects.filter(is_published=True)
          .select_related("brand").only("slug", "name", "brand__name", "brand__slug"))
    for device in qs.iterator(chunk_size=500):
        for _, regex in _alias_patterns(device.brand.name, device.name):
            for hit in regex.finditer(message):
                matches.append({
                    "slug": device.slug, "name": device.name,
                    "brand": device.brand.slug, "start": hit.start(), "end": hit.end(),
                })
    # Prefer longest textual matches, so "Galaxy S26 Ultra" never contributes
    # an extra match to "Galaxy S26".
    selected = []
    used_slugs = set()
    for candidate in sorted(matches, key=lambda x: (-(x["end"] - x["start"]), x["start"], x["slug"])):
        if candidate["slug"] in used_slugs:
            continue
        if any(candidate["start"] < m["end"] and m["start"] < candidate["end"] for m in selected):
            continue
        selected.append(candidate)
        used_slugs.add(candidate["slug"])
    return sorted(selected, key=lambda x: x["start"])[:max_matches]


def _quality(value):
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return round(min(100.0, max(0.0, number)), 1) if number > 0 else None


def _variant_scores(variant):
    return {key: _quality(getattr(variant, f"{key}_score")) for key in QUALITY_DIMENSIONS}


def _variant_facts(variant):
    facts = []
    if variant.chipset:
        facts.append(f"Chipset: {variant.chipset}")
    if variant.battery_mah:
        facts.append(f"Battery capacity: {variant.battery_mah} mAh (not battery-life testing)")
    if variant.display_refresh_hz:
        facts.append(f"Refresh rate: {variant.display_refresh_hz} Hz")
    facts.append(f"Memory: {variant.ram_gb} GB RAM / {variant.storage_gb} GB storage")
    return facts


def specs_recommendations(criteria, *, exclude_slugs=()):
    """Read-only specs-based shortlist; never assume price or market eligibility."""
    priorities = [x for x in criteria.get("priorities", []) if x in QUALITY_DIMENSIONS]
    if not priorities:
        return []
    variants = (DeviceVariant.objects.filter(device__is_published=True)
                .exclude(device__status__in=("rumored", "announced"))
                .select_related("device", "device__brand"))
    if criteria.get("brand"):
        variants = variants.filter(device__brand__slug__iexact=criteria["brand"])
    if criteria.get("ram_min"):
        variants = variants.filter(ram_gb__gte=criteria["ram_min"])
    if criteria.get("storage_min"):
        variants = variants.filter(storage_gb__gte=criteria["storage_min"])
    if exclude_slugs:
        variants = variants.exclude(device__slug__in=exclude_slugs)
    # Order by the primary requested editorial signal before bounding work.
    # Unknown values remain unknown, never treated as excellent results.
    primary = priorities[0]
    variants = variants.order_by(f"-{primary}_score", "device__slug")[:MAX_DISCOVERY_VARIANTS]
    by_device = {}
    for variant in variants:
        scores = _variant_scores(variant)
        available = [scores[key] for key in priorities if scores[key] is not None]
        missing = [key for key in priorities if scores[key] is None]
        fit = round(sum(available) / len(available), 1) if available else None
        candidate = (fit is None, len(missing), -(fit or 0), variant.device.slug)
        existing = by_device.get(variant.device_id)
        if existing is None or candidate < existing[0]:
            by_device[variant.device_id] = (candidate, variant, fit, scores, missing)
    ranked = sorted(by_device.values(), key=lambda item: item[0])[:criteria.get("max_results", 3)]
    result = []
    for _, variant, fit, scores, missing in ranked:
        device = variant.device
        strengths = [
            f"{key.title()} editorial score: {scores[key]:.0f}/100"
            for key in priorities if scores[key] is not None
        ]
        if not strengths:
            strengths = _variant_facts(variant)[:2]
        result.append({
            "slug": device.slug, "brand": device.brand.name, "name": device.name,
            "summary": device.summary, "primary_image_url": device.primary_image_url,
            "last_verified_at": device.last_verified_at.isoformat() if device.last_verified_at else None,
            "editorial_fit": fit, "dimension_scores": scores, "missing_scores": missing,
            "strengths": strengths, "facts": _variant_facts(variant),
            "price_status": "not_verified_for_filters",
            "evidence_label": "Catalog editorial estimates, not independently measured benchmarks",
        })
    return result


def compare_catalog_phones(slugs, priorities=()):
    """Compare two specific published models using documented local scores."""
    unique = list(dict.fromkeys(s for s in slugs if isinstance(s, str)))[:2]
    if len(unique) != 2:
        return None
    phones = list(Device.objects.filter(is_published=True, slug__in=unique)
                  .select_related("brand").prefetch_related("variants"))
    by_slug = {p.slug: p for p in phones}
    if len(by_slug) != 2:
        return None
    devices = [by_slug[s] for s in unique]
    def snapshot(device):
        variants = list(device.variants.all())
        # A consistent documented variant per phone, not mixing camera from
        # one variant and battery from another.
        def strength(variant):
            scores = _variant_scores(variant)
            known = [x for x in scores.values() if x is not None]
            return (len(known), sum(known), variant.ram_gb, variant.storage_gb)
        variant = max(variants, key=strength) if variants else None
        return {"slug": device.slug, "name": f"{device.brand.name} {device.name}",
                "variant": variant, "scores": _variant_scores(variant) if variant else {
                    k: None for k in QUALITY_DIMENSIONS}}
    first, second = (snapshot(p) for p in devices)
    dimensions = list(dict.fromkeys(
        [x for x in priorities if x in QUALITY_DIMENSIONS] + list(QUALITY_DIMENSIONS)
    ))
    rows = []
    for key in dimensions:
        a, b = first["scores"][key], second["scores"][key]
        leader = first["slug"] if a is not None and b is not None and a > b else (
            second["slug"] if a is not None and b is not None and b > a else None)
        note = ("Editorial catalog scores only; not an independent benchmark"
                if a is not None and b is not None else
                "Insufficient comparable scores; no winner can be established")
        rows.append({"dimension": key, "first_score": a, "second_score": b,
                     "leader_slug": leader, "note": note})
    return {
        "phones": [{"slug": p["slug"], "name": p["name"]} for p in (first, second)],
        "dimensions": rows,
        "notice": "Compared local catalog estimates only. Price, PTA status and live availability are not inferred.",
    }
