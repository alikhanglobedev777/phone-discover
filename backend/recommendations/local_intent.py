"""Conservative, deterministic English / Roman Urdu phone-shopping intent extraction.

Not an LLM and not conversation memory. Extract only explicit requirements, and
never turn a hardware capacity into a budget. Ambiguous requests remain visible
for callers to clarify rather than guessing.
"""

import re
from decimal import Decimal

from catalog.models import MarketPriceObservation

_AMOUNT = re.compile(
    r"(?<![\w.])(?P<prefix>pkr\s*|rs\.?\s*|₨\s*)?"
    r"(?P<number>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
    r"(?P<unit>lakh(?:s)?|lac(?:s)?|hazaar|hazar|thousand|k)?\b",
    re.IGNORECASE,
)
_MONEY_WORDS = re.compile(
    r"\b(?:budget|under|below|within|maximum|max|upto|up\s+to|less\s+than|"
    r"tak|andar|kam|rupees|rupay|pkr|rs)\b|₨",
    re.IGNORECASE,
)
_COMBINED = re.compile(
    r"(?<!\w)(\d+(?:\.\d+)?)\s*(?:lakh|lac)(?:s)?\s+"
    r"(\d+(?:\.\d+)?)\s*(?:hazar|hazaar|thousand|k)\b",
    re.IGNORECASE,
)

_PRIORITY_PATTERNS = {
    "camera": r"\b(?:camera|cameras|photo|photos|photography|portrait|selfie|video|tasveer|tasweeren)\b",
    "gaming": r"\b(?:gaming|games?|pubg|codm|genshin|performance|free\s+fire|fps)\b",
    "battery": r"\b(?:battery|backup|battery\s+life|battery\s+timing|long\s+lasting)\b",
    "display": r"\b(?:display|screen|amoled|oled|refresh\s+rate|120\s*hz|144\s*hz)\b",
    "value": r"\b(?:value|sasta|sasti|cheap|affordable|paisa\s+vasool)\b",
}
_CITY_NAMES = (
    "Lahore", "Karachi", "Islamabad", "Rawalpindi", "Faisalabad", "Peshawar",
    "Multan", "Gujranwala", "Sialkot", "Hyderabad", "Quetta",
)
_BRAND_ALIASES = {
    "samsung": "samsung", "xiaomi": "xiaomi", "redmi": "redmi", "poco": "poco",
    "iphone": "apple", "apple": "apple", "pixel": "google", "google": "google",
    "oppo": "oppo", "vivo": "vivo", "realme": "realme", "infinix": "infinix",
    "tecno": "tecno", "oneplus": "oneplus", "motorola": "motorola",
    "honor": "honor", "nothing": "nothing", "itel": "itel",
}
_CONDITION_PATTERNS = {
    MarketPriceObservation.Condition.BOX_PACK:
        r"\b(?:box[ -]?pack(?:ed)?|sealed|brand[ -]?new|new|naya|nayi)\b",
    MarketPriceObservation.Condition.OPEN_BOX:
        r"\bopen[ -]?box\b",
    MarketPriceObservation.Condition.USED:
        r"\b(?:used|second[ -]?hand|pre[ -]?owned|purana|purani)\b",
    MarketPriceObservation.Condition.REFURBISHED:
        r"\b(?:refurbished|renewed)\b",
}


def _money(number: str, unit: str | None) -> Decimal:
    value = Decimal(number.replace(",", ""))
    unit = (unit or "").casefold()
    if unit in ("lakh", "lakhs", "lac", "lacs"):
        return value * 100000
    if unit in ("hazaar", "hazar", "thousand", "k"):
        return value * 1000
    return value


def parse_pakistan_intent(message: str) -> dict:
    text = (message or "").strip().casefold()
    result = {"priorities": []}
    if not text:
        return result

    if re.search(r"(?:\busd\b|\baed\b|\beur\b|\binr\b|\$|€|£)", text):
        result["foreign_currency_requested"] = True

    for dimension, pattern in _PRIORITY_PATTERNS.items():
        if re.search(pattern, text):
            result["priorities"].append(dimension)

    match = _COMBINED.search(text)
    if match:
        result["budget_pkr"] = (
            Decimal(match.group(1)) * 100000 + Decimal(match.group(2)) * 1000
        )
    else:
        for m in _AMOUNT.finditer(text):
            left = text[max(0, m.start() - 20):m.start()]
            right = text[m.end():m.end() + 20]
            unit, prefix = m.group("unit"), m.group("prefix")
            # Only interpret a number as price when it has a monetary unit,
            # explicit currency marker or a nearby budget phrase. Bare '8GB'
            # and '256GB' must never become budgets.
            left_context = _MONEY_WORDS.search(left)
            right_context = _MONEY_WORDS.search(right)
            if (unit or prefix or left_context or right_context) and not re.match(
                r"\s*(?:gb|mp|mah|hz)\b", right
            ):
                amount = _money(m.group("number"), unit)
                if 1000 <= amount <= Decimal("100000000"):
                    result["budget_pkr"] = amount
                    break

    found_conditions = [
        condition for condition, pattern in _CONDITION_PATTERNS.items()
        if re.search(pattern, text)
    ]
    if len(found_conditions) == 1:
        result["condition"] = found_conditions[0]
    elif len(found_conditions) > 1:
        result["ambiguous_condition"] = True

    if re.search(r"\b(?:non[ -]?pta|without\s+pta|unapproved\s+pta)\b", text):
        result["pta_status"] = MarketPriceObservation.PTAStatus.NON_PTA
    elif re.search(r"\bcpid\b", text):
        result["pta_status"] = MarketPriceObservation.PTAStatus.CPID
    elif re.search(r"\bpatched\b", text):
        result["pta_status"] = MarketPriceObservation.PTAStatus.PATCHED
    elif re.search(r"\bpta\b", text):
        result["pta_status"] = MarketPriceObservation.PTAStatus.APPROVED

    if re.search(r"\b(?:verified\s+pta|pta\s+verified|pta\s+checked|independently\s+checked)\b", text):
        result["pta_verification"] = MarketPriceObservation.PTAVerification.CHECKED

    for city in _CITY_NAMES:
        if re.search(rf"\b{re.escape(city.casefold())}\b", text):
            result["city"] = city
            break

    # Only explicit RAM/storage qualifiers. '80GB data' isn't storage.
    for label, pattern in (
        ("ram_min", r"\b(\d{1,3})\s*gb\s*ram\b|\bram\s*(\d{1,3})\s*gb\b"),
        ("storage_min", r"\b(\d{2,5})\s*gb\s*(?:storage|rom)\b|\b(?:storage|rom)\s*(\d{2,5})\s*gb\b"),
    ):
        m = re.search(pattern, text)
        if m:
            result[label] = int(m.group(1) or m.group(2))

    for alias, brand in _BRAND_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text):
            result["brand"] = brand
            break
    result["response_language"] = (
        "roman_urdu" if re.search(r"\b(?:mujhe|chahiye|batao|btao|wala|wali|tak|mein|kaunsa|konsa|sabse)\b", text)
        else "english"
    )
    return result
