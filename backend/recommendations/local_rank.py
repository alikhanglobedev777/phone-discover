"""DB-first, read-only Pakistani recommendations.

Reuses Patch 05's exact-variant, evidence-gated search. This service never
calls an LLM, guesses a market price or writes to the product catalog.
Scores describe a local editorial fit heuristic, NOT probabilities or measured
hardware benchmarks.
"""

from decimal import Decimal

from catalog.search import search_local_catalog
from .local_intent import parse_pakistan_intent

DEFAULT_DIMENSIONS = ("camera", "gaming", "battery", "display", "value")
MAX_LOCAL_CANDIDATES = 250


def interpret_local_request(validated: dict) -> dict:
    """Merge explicit client filters over conservative natural-language fields."""
    message = validated["message"].strip()
    parsed = parse_pakistan_intent(message)
    if parsed.get("foreign_currency_requested"):
        raise ValueError("This endpoint compares Pakistani PKR prices only; remove the foreign currency.")
    if parsed.get("ambiguous_condition") and "condition" not in validated:
        raise ValueError("Please select one phone condition: box pack, open box, used or refurbished.")
    fields = (
        "budget_pkr", "condition", "grade", "pta_status", "pta_verification",
        "city", "brand", "device_query", "priorities", "ram_min", "storage_min",
    )
    criteria = {key: validated.get(key, parsed.get(key)) for key in fields}
    criteria.update({
        "session_id": validated["session_id"],
        "message": message,
        "country_code": "PK",
        "currency": "PKR",
        "strict_budget": validated["strict_budget"],
        "max_results": validated["max_results"],
        "response_language": parsed.get("response_language", "english"),
    })
    criteria["priorities"] = criteria["priorities"] or []
    if criteria.get("grade") and criteria.get("condition") not in ("used", "refurbished"):
        raise ValueError("A condition grade requires used or refurbished phones.")
    if criteria.get("pta_verification") == "checked" and criteria.get("pta_status") == "unknown":
        raise ValueError("Independently checked PTA status cannot be unknown.")
    return criteria


def _bounded(value) -> float | None:
    if value is None:
        return None
    score = float(value)
    return round(max(0.0, min(100.0, score)), 2) if score > 0 else None


def _quality_scores(variant: dict, price: dict | None, budget: Decimal | None):
    camera = _bounded(variant["camera_score"])
    gaming = _bounded(variant["gaming_score"])
    battery = _bounded(variant["battery_score"])
    # Refresh rate is only one part of display quality, never a benchmark.
    display = None
    if variant.get("display_refresh_hz"):
        display = round(min(100.0, max(0.0, float(variant["display_refresh_hz"]) / 144 * 100)), 2)
    value = None
    if price and budget and budget > 0:
        high = Decimal(price["observed_max_pkr"])
        value = round(max(0.0, min(100.0, 130 - 70 * float(high / budget))), 2)
    return {"camera": camera, "gaming": gaming, "battery": battery, "display": display, "value": value}


def _fit_score(scores, priorities, budget):
    dimensions = list(dict.fromkeys(priorities)) if priorities else ["camera", "gaming", "battery", "display"]
    if budget is not None and not priorities:
        dimensions.append("value")
    known = [key for key in dimensions if scores[key] is not None]
    missing = [key for key in dimensions if scores[key] is None]
    # Re-normalization to available signals must not be presented as high
    # certainty: ranking penalizes missing dimensions and labels the gap.
    score = round(sum(scores[key] for key in known) / len(known), 1) if known else None
    return score, missing


def rank_pakistan_phones(criteria: dict):
    priorities = criteria["priorities"]
    budget = criteria.get("budget_pkr")
    primary = priorities[0] if priorities else "price"
    sorting = primary if primary in ("camera", "gaming", "battery") else "price"
    search_params = {
        "require_price": True,
        "sort": sorting,
        "page_size": 50,
        "page": 1,
        "budget_mode": "strict" if criteria["strict_budget"] else "possible",
    }
    for key in (
        "budget_pkr", "condition", "grade", "pta_status", "pta_verification",
        "city", "ram_min", "storage_min", "brand",
    ):
        if criteria.get(key) is not None:
            search_params[key] = criteria[key]
    if criteria.get("device_query"):
        search_params["q"] = criteria["device_query"]
    all_cards = []
    searched = 0
    total_count = None
    # Bounded collection: never pretend a partially scanned catalog is complete.
    for page in range(1, MAX_LOCAL_CANDIDATES // 50 + 1):
        search_params["page"] = page
        page_data = search_local_catalog(search_params)
        total_count = page_data["count"]
        all_cards.extend(page_data["results"])
        searched += len(page_data["results"])
        if not page_data["has_more"]:
            break

    ranked = []
    for card in all_cards:
        scores = _quality_scores(card["variant"], card["price_observation"], budget)
        fit, missing = _fit_score(scores, priorities, budget)
        price = card["price_observation"]
        known = [dimension for dimension in (priorities or DEFAULT_DIMENSIONS) if scores[dimension] is not None]
        strengths = [
            f"{key.title()} catalog fit {scores[key]:.0f}/100"
            for key in sorted(known, key=lambda k: scores[k], reverse=True)[:2]
        ]
        tradeoffs = []
        if missing:
            tradeoffs.append("Not enough catalog scoring evidence for: " + ", ".join(missing))
        if price["budget_fit"] == "possibly_within_budget":
            tradeoffs.append("Only the low end of the observed price range fits your budget")
        if price["pta_status"] == "approved" and price["pta_verification"] != "checked":
            tradeoffs.append("PTA approval is reported, not independently confirmed")
        if not tradeoffs:
            tradeoffs.append("Observed asking prices and availability may change")
        ranked.append({
            "device": {
                "id": card["id"], "slug": card["slug"], "name": card["name"],
                "brand": card["brand"]["name"], "summary": card["summary"],
                "status": card["status"], "primary_image_url": card["primary_image_url"],
                "detail_url": f"/?device={card['slug']}",
                "detail_api_url": card["detail_api_url"],
            },
            "variant": card["variant"],
            "market_price": price,
            "fit_score": fit,
            "fit_score_is_probability": False,
            "scoring_basis": "editorial_catalog_estimates_not_independent_benchmarks",
            "dimension_scores": scores,
            "missing_score_evidence": missing,
            "strengths": strengths,
            "tradeoffs": tradeoffs,
        })

    def ordering(item):
        high = Decimal(item["market_price"]["observed_max_pkr"])
        missing_count = len(item["missing_score_evidence"])
        # An unknown score must not outrank a well-evidenced phone merely
        # because the available dimensions average high.
        return (item["fit_score"] is None, missing_count, -(item["fit_score"] or 0), high,
                item["device"]["slug"])

    ranked.sort(key=ordering)
    shortlisted = ranked[:criteria["max_results"]]
    for index, item in enumerate(shortlisted, 1):
        item["rank"] = index
        item["recommended"] = index == 1
    truncated = total_count is not None and total_count > searched
    insufficient = not shortlisted or len(shortlisted) < criteria["max_results"]
    missing_scores = any(item["missing_score_evidence"] for item in shortlisted)
    return {
        "count": total_count or 0,
        "searched_count": searched,
        "coverage_incomplete": truncated,
        "needs_research": insufficient or truncated or missing_scores,
        "research_reason": (
            "no_matching_local_evidence" if not shortlisted else
            "catalog_scan_limited" if truncated else
            "limited_local_evidence" if insufficient else
            "insufficient_score_evidence" if missing_scores else None
        ),
        "results": shortlisted,
    }


def local_explanation(criteria, summary):
    if not summary["results"]:
        return (
            "Is budget aur condition ke liye verified local price data nahi mila. "
            "Internet research ke liye 'Request Gemini web research' select karein."
            if criteria["response_language"] == "roman_urdu" else
            "I found no published phone with fresh, permitted Pakistani price evidence matching your requirements. "
            "To check unverified external sources, select 'Request Gemini web research' and ask again."
        )
    best = summary["results"][0]
    name = f"{best['device']['brand']} {best['device']['name']}".strip()
    price = best["market_price"]
    range_str = f"PKR {price['observed_min_pkr']}–{price['observed_max_pkr']}"
    if criteria["response_language"] == "roman_urdu":
        return (f"Local data ke mutabiq {name} aik option hai ({range_str}). "
                "Yeh observed asking price hai, guaranteed market rate nahi. "
                "PTA status aur handset condition khud verify karein.")
    return (
        f"Based on available catalog estimates, {name} is a leading local option "
        f"with an observed asking-price range of {range_str}. "
        "This is not a live offer; verify handset condition and PTA status independently."
    )
