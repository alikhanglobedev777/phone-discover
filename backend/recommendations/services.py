import re
from decimal import Decimal
from difflib import SequenceMatcher

from catalog.models import Device, DeviceVariant

DIMENSIONS = ("camera", "gaming", "battery", "display", "value")
DEFAULT_WEIGHTS = {
    "camera": 0.22,
    "gaming": 0.20,
    "battery": 0.20,
    "display": 0.16,
    "value": 0.22,
}
PRIORITY_KEYWORDS = {
    "camera": ("camera", "photo", "photography", "video", "portrait", "selfie"),
    "gaming": ("gaming", "game", "performance", "fps", "esports"),
    "battery": ("battery", "battery life", "long lasting", "endurance"),
    "display": ("display", "screen", "amoled", "refresh rate", "bright"),
    "value": ("value", "cheap", "affordable", "budget", "deal"),
}
CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "₨": "PKR"}
DEVICE_LOOKUP_PATTERNS = (
    r"^\s*tell\s+me\s+about\s+(?P<query>.+?)\s*[?.!]*$",
    r"^\s*(?:show|give)\s+me\s+(?:details|information|specs|specifications)\s+(?:about|for|of|on)\s+(?P<query>.+?)\s*[?.!]*$",
    r"^\s*(?:details|information|specs|specifications)\s+(?:about|for|of|on)\s+(?P<query>.+?)\s*[?.!]*$",
    r"^\s*what\s+about\s+(?P<query>.+?)\s*[?.!]*$",
)
RECOMMENDATION_WORDS = {
    "any",
    "best",
    "below",
    "budget",
    "cheap",
    "compare",
    "mobile",
    "mobiles",
    "phone",
    "phones",
    "recommend",
    "recommendation",
    "suggest",
    "top",
    "under",
    "versus",
    "vs",
}


def parse_message(message: str) -> dict:
    original_text = (message or "").strip()
    text = original_text.lower()
    priorities = [
        priority
        for priority, keywords in PRIORITY_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    ]
    budget_match = re.search(
        r"(?:under|below|max(?:imum)?|budget(?:\s+of)?|up\s+to)\s*"
        r"(?:(usd|eur|gbp|pkr|inr|aed)|([$€£₨]))?\s*"
        r"([0-9]+(?:[,.][0-9]+)?)",
        text,
        flags=re.IGNORECASE,
    )
    parsed = {"priorities": priorities, "intent": "recommendation"}
    if budget_match:
        parsed["budget"] = Decimal(budget_match.group(3).replace(",", ""))
        currency_code = budget_match.group(1)
        currency_symbol = budget_match.group(2)
        if currency_code:
            parsed["currency"] = currency_code.upper()
        elif currency_symbol:
            parsed["currency"] = CURRENCY_SYMBOLS[currency_symbol]

    device_query = None
    for pattern in DEVICE_LOOKUP_PATTERNS:
        lookup_match = re.match(pattern, original_text, flags=re.IGNORECASE)
        if lookup_match:
            device_query = lookup_match.group("query").strip(" .?!")
            break

    words = re.findall(r"[a-z0-9]+", text)
    if (
        not device_query
        and 2 <= len(words) <= 8
        and not priorities
        and not budget_match
        and not RECOMMENDATION_WORDS.intersection(words)
    ):
        device_query = original_text.strip(" .?!")

    if device_query:
        parsed["intent"] = "device_lookup"
        parsed["device_query"] = device_query
    return parsed


def _normalise_device_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))


def _device_match_score(query: str, device: Device) -> float:
    query_text = _normalise_device_text(query)
    aliases = {
        _normalise_device_text(device.name),
        _normalise_device_text(f"{device.brand.name} {device.name}"),
        _normalise_device_text(device.slug.replace("-", " ")),
    }
    aliases.discard("")
    if query_text in aliases:
        return 1.0
    if len(query_text.split()) >= 2 and any(
        query_text in alias or alias in query_text for alias in aliases
    ):
        return 0.95
    return max(
        (SequenceMatcher(None, query_text, alias).ratio() for alias in aliases),
        default=0.0,
    )


def _matching_device_id(query: str):
    best_device_id = None
    best_score = 0.0
    devices = Device.objects.filter(is_published=True).select_related("brand")
    for device in devices:
        score = _device_match_score(query, device)
        if score > best_score:
            best_device_id = device.id
            best_score = score
    return best_device_id if best_score >= 0.78 else None


def _normalise_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in weights.values())
    if total <= 0:
        return DEFAULT_WEIGHTS.copy()
    return {key: round(max(0.0, value) / total, 4) for key, value in weights.items()}


def build_criteria(data: dict) -> dict:
    parsed = parse_message(data.get("message", ""))
    priorities = list(dict.fromkeys(data.get("priorities") or parsed.get("priorities") or []))
    weights = DEFAULT_WEIGHTS.copy()
    if priorities:
        weights = {dimension: 0.08 for dimension in DIMENSIONS}
        for priority in priorities:
            weights[priority] += 1.0

    explicit_weights = {
        "camera": data.get("camera_weight"),
        "gaming": data.get("gaming_weight"),
        "battery": data.get("battery_weight"),
        "value": data.get("value_weight"),
    }
    for dimension, value in explicit_weights.items():
        if value is not None:
            weights[dimension] = float(value)

    budget = data.get("budget")
    if budget is None:
        budget = parsed.get("budget")

    return {
        "session_id": data["session_id"],
        "message": data.get("message", "").strip(),
        "intent": parsed.get("intent", "recommendation"),
        "device_query": parsed.get("device_query", ""),
        "budget": budget,
        "currency": data.get("currency") or parsed.get("currency") or "USD",
        "country_code": data.get("country_code", "US").upper(),
        "priorities": priorities,
        "weights": _normalise_weights(weights),
        "preferred_brands": [brand.strip() for brand in data.get("preferred_brands", [])],
        "excluded_brands": [brand.strip() for brand in data.get("excluded_brands", [])],
        "ram_min": data.get("ram_min", 0),
        "storage_min": data.get("storage_min", 0),
        "strict_budget": data.get("strict_budget", True),
    }


def _bounded_score(value: float, maximum: float = 100.0) -> float:
    return max(0.0, min(100.0, (value / maximum) * 100.0))


def _value_score(price: Decimal | None, budget: Decimal | None) -> float:
    if not price or not budget:
        return 60.0
    ratio = float(price / budget)
    return max(0.0, min(100.0, 130.0 - (ratio * 70.0)))


def _select_offer(variant, country: str, currency: str):
    offers = [offer for offer in variant.offers.all() if offer.is_available]
    preference_groups = (
        [offer for offer in offers if offer.country_code == country and offer.currency == currency],
        [offer for offer in offers if offer.country_code == country],
        [offer for offer in offers if offer.currency == currency],
        offers,
    )
    for candidates in preference_groups:
        if candidates:
            offer = min(candidates, key=lambda item: item.price)
            return offer, offer.country_code == country
    return None, False


def _result_insights(criteria: dict, scores: dict[str, float], offer, local_offer: bool):
    requested = criteria["priorities"] or list(DIMENSIONS)
    ranked_dimensions = sorted(requested, key=lambda dimension: scores[dimension], reverse=True)
    strengths = [
        f"{scores[dimension]:.0f}/100 {dimension} fit"
        for dimension in ranked_dimensions[:2]
    ]
    if criteria.get("budget") and offer:
        saving = criteria["budget"] - offer.price
        if saving >= 0:
            strengths.append(f"{offer.currency} {saving:.0f} under budget")

    tradeoffs = []
    weakest = min(requested, key=lambda dimension: scores[dimension])
    if scores[weakest] < 80:
        tradeoffs.append(f"{weakest.title()} is the weaker part of this match")
    if offer and not local_offer:
        tradeoffs.append("Price is from another market")
    if (
        criteria.get("intent") == "device_lookup"
        and criteria.get("budget")
        and offer
        and offer.currency == criteria["currency"]
        and offer.price > criteria["budget"]
    ):
        difference = offer.price - criteria["budget"]
        tradeoffs.append(f"{offer.currency} {difference:.0f} above the selected budget")
    if not offer:
        tradeoffs.append("No active seller offer is currently verified")
    return strengths[:3], tradeoffs[:2]


def rank_variants(criteria: dict) -> list[dict]:
    variants = (
        DeviceVariant.objects.filter(device__is_published=True)
        .select_related("device__brand")
        .prefetch_related("offers")
    )
    preferred = {brand.casefold() for brand in criteria["preferred_brands"]}
    excluded = {brand.casefold() for brand in criteria["excluded_brands"]}
    country = criteria["country_code"]
    currency = criteria["currency"]
    budget = criteria.get("budget")
    weights = criteria["weights"]
    is_device_lookup = criteria.get("intent") == "device_lookup"
    if is_device_lookup:
        device_id = _matching_device_id(criteria.get("device_query", ""))
        if device_id is None:
            return []
        variants = variants.filter(device_id=device_id)
    ranked = []

    for variant in variants:
        brand_name = variant.device.brand.name.casefold()
        if not is_device_lookup:
            if preferred and brand_name not in preferred:
                continue
            if brand_name in excluded:
                continue
            if variant.ram_gb < criteria["ram_min"] or variant.storage_gb < criteria["storage_min"]:
                continue

        offer, local_offer = _select_offer(variant, country, currency)
        if not is_device_lookup and budget and criteria["strict_budget"]:
            if not offer or offer.currency != currency or offer.price > budget:
                continue

        scores = {
            "camera": float(variant.camera_score),
            "gaming": float(variant.gaming_score),
            "battery": float(variant.battery_score),
            "display": _bounded_score(float(variant.display_refresh_hz or 60), 144),
            "value": _value_score(offer.price if offer and offer.currency == currency else None, budget),
        }
        strengths, tradeoffs = _result_insights(criteria, scores, offer, local_offer)
        if is_device_lookup:
            match_score = 100.0
            strengths = ["Exact catalog match", *strengths[:2]]
        else:
            match_score = sum(scores[dimension] * weights[dimension] for dimension in DIMENSIONS)
            if local_offer:
                match_score += 2.0
        ranked.append(
            {
                "device": variant.device,
                "variant": variant,
                "offer": offer,
                "local_offer": local_offer,
                "score": round(min(100.0, match_score), 2),
                "dimension_scores": {key: round(value, 1) for key, value in scores.items()},
                "strengths": strengths,
                "tradeoffs": tradeoffs,
            }
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:1] if is_device_lookup else ranked[:3]


def serialise_results(results: list[dict]) -> list[dict]:
    output = []
    for index, result in enumerate(results):
        device = result["device"]
        variant = result["variant"]
        offer = result["offer"]
        output.append(
            {
                "rank": index + 1,
                "recommended": index == 0,
                "score": result["score"],
                "match_percentage": round(result["score"]),
                "device": {
                    "name": device.name,
                    "brand": device.brand.name,
                    "slug": device.slug,
                    "summary": device.summary,
                    "status": device.status,
                    "primary_image_url": device.primary_image_url,
                    "detail_url": f"/?device={device.slug}",
                },
                "variant": {
                    "name": variant.name,
                    "ram_gb": variant.ram_gb,
                    "storage_gb": variant.storage_gb,
                    "battery_mah": variant.battery_mah,
                    "display_refresh_hz": variant.display_refresh_hz,
                    "chipset": variant.chipset,
                    "camera_score": float(variant.camera_score),
                    "gaming_score": float(variant.gaming_score),
                    "battery_score": float(variant.battery_score),
                },
                "dimension_scores": result["dimension_scores"],
                "strengths": result["strengths"],
                "tradeoffs": result["tradeoffs"],
                "offer": None
                if not offer
                else {
                    "country_code": offer.country_code,
                    "currency": offer.currency,
                    "price": str(offer.price),
                    "seller_name": offer.seller_name,
                    "product_url": offer.product_url,
                    "is_local": result["local_offer"],
                },
                "reason": result["strengths"][0]
                if result["strengths"]
                else "Strong overall match for the selected requirements",
            }
        )
    return output


def deterministic_explanation(criteria: dict, results: list[dict]) -> str:
    if not results:
        if criteria.get("intent") == "device_lookup":
            query = criteria.get("device_query") or criteria.get("message") or "That phone"
            return (
                f"I could not find '{query}' in the current catalog. "
                "Add and publish the phone in Django admin before I recommend or describe it."
            )
        budget_text = (
            f" within {criteria['currency']} {criteria['budget']}"
            if criteria.get("budget")
            else ""
        )
        return (
            f"I could not find an exact catalog match{budget_text}. "
            "Try increasing the budget, reducing minimum memory, or allowing more brands."
        )
    best = results[0]
    brand = best["device"]["brand"]
    device_name = best["device"]["name"]
    display_name = (
        device_name
        if device_name.casefold().startswith(brand.casefold())
        else f"{brand} {device_name}"
    )
    if criteria.get("intent") == "device_lookup":
        return (
            f"I found {display_name} in the catalog. "
            f"The listed variant is {best['variant']['name']} and its match record is ready below."
        )
    strengths = ", ".join(best["strengths"][:2]).lower()
    return (
        f"{display_name} is the strongest match at "
        f"{best['match_percentage']}%. It stands out for {strengths}. "
        "The alternatives below trade some of that fit for different strengths or pricing."
    )


def json_ready(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return str(value) if value.__class__.__name__ == "UUID" else value
