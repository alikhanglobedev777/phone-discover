"""Deterministic dialogue routing for catalog-based phone conversations.

No generated model facts or transcript retention. Prior shortlist references are
bounded published slugs and are used ONLY when the user asks to refine that list.
"""
import re


_COMPARE = re.compile(
    r"\b(?:compare|comparison|versus|vs\.?|which\s+(?:one|phone)(?:\s+\w+){0,6}\s+better|"
    r"which\s+is\s+better|better\s+(?:camera|battery|gaming)\s+between)\b", re.I,
)
_FILTER_SCOPE = re.compile(
    r"\b(?:only|sirf|just|filter|among\s+(?:these|those|them)|"
    r"from\s+(?:these|those|them)|in\s+(?:these|those|them))\b", re.I,
)
_NEW_CATEGORY = re.compile(r"\b(?:best|recommend|suggest|top)\b", re.I)
_NEW_CATEGORY_EXCLUSION = re.compile(r"\b(?:about|details|specs)\b", re.I)
_PLAIN_BRAND = re.compile(r"\b(?:phones?|models?|options?|mein|batao|show|only)\b", re.I)


def comparison_requested(message):
    return bool(_COMPARE.search(message))


def refine_previous_list(message, parsed, supplied_fields):
    """A constraints-only follow-up must filter previous phones, not find others."""
    if not _FILTER_SCOPE.search(message):
        return False
    constrained = ("budget_pkr", "pta_status", "pta_verification", "condition",
                   "grade", "city", "ram_min", "storage_min")
    return any(key in parsed or key in supplied_fields for key in constrained)


def new_category_request(message):
    return bool(_NEW_CATEGORY.search(message) and not _NEW_CATEGORY_EXCLUSION.search(message))


def plain_brand_request(message, parsed):
    """An explicit brand-only prompt replaces a previously focused exact model."""
    return bool(parsed.get("brand") and not parsed.get("device_query")
                and _PLAIN_BRAND.search(message))
