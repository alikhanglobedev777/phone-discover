"""Bounded opt-in conversation context for the Pakistan local search endpoint.

A random UUID is a bearer handle: clients must protect it and use HTTPS.
Only structured preferences are stored; the previous chat transcript is not.
"""

import re
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .local_intent import parse_pakistan_intent
from .local_rank import interpret_local_request
from .models import ConversationContext, RecommendationQuery
from .services import json_ready

PREFERENCE_FIELDS = (
    "budget_pkr", "condition", "grade", "pta_status", "pta_verification",
    "city", "brand", "priorities", "ram_min", "storage_min",
    "strict_budget", "max_results",
)
RESET_PATTERN = re.compile(r"\b(?:start\s+over|reset(?:\s+chat|\s+preferences)?|new\s+search)\b", re.I)
CLEAR_BRAND = re.compile(r"\b(?:any\s+brand|no\s+brand\s+preference|koi\s+bhi\s+brand)\b", re.I)
CLEAR_BUDGET = re.compile(r"\b(?:no\s+budget|any\s+budget|remove\s+budget)\b", re.I)
CLEAR_CITY = re.compile(r"\b(?:any\s+city|anywhere\s+in\s+pakistan)\b", re.I)


def lifetime_days():
    return max(1, min(90, int(getattr(settings, "CONVERSATION_RETENTION_DAYS", 7))))


def previous_context(session_id):
    state = ConversationContext.objects.filter(session_id=session_id).first()
    if state is None or state.updated_at < timezone.now() - timedelta(days=lifetime_days()):
        return {}
    data = dict(state.preferences) if isinstance(state.preferences, dict) else {}
    if data.get("budget_pkr") is not None:
        try:
            data["budget_pkr"] = Decimal(str(data["budget_pkr"]))
        except (ValueError, ArithmeticError):
            data.pop("budget_pkr", None)
    return data


def build_conversation_criteria(validated, supplied_fields, previous):
    """Merge only newly explicit facts. Serializer defaults must not overwrite memory."""
    message = validated["message"].strip()
    intent_text = re.sub(r"\bnew\s+search\b", "search", message, flags=re.I)
    parsed = parse_pakistan_intent(intent_text)
    if parsed.get("foreign_currency_requested"):
        raise ValueError("This endpoint compares Pakistani PKR prices only; remove the foreign currency.")
    if parsed.get("ambiguous_condition") and "condition" not in supplied_fields:
        raise ValueError("Please select one phone condition: box pack, open box, used or refurbished.")

    merged = {key: previous[key] for key in PREFERENCE_FIELDS if key in previous}
    if RESET_PATTERN.search(message):
        merged.clear()
    for key, pattern in (("brand", CLEAR_BRAND), ("budget_pkr", CLEAR_BUDGET), ("city", CLEAR_CITY)):
        if pattern.search(message):
            merged.pop(key, None)
    for key in PREFERENCE_FIELDS:
        # The intent parser always returns "priorities": [] even when a turn
        # mentions no priority. Do not erase a prior preference on brand-only
        # follow-ups; a new non-empty priority still replaces the old one.
        if key in parsed and (key != "priorities" or parsed[key]):
            merged[key] = parsed[key]
        if key in supplied_fields:
            merged[key] = validated[key]
    # A changed condition cannot carry a prior condition grade into box pack.
    if merged.get("condition") not in ("used", "refurbished"):
        merged.pop("grade", None)
    merged.update({
        "message": message,
        "session_id": validated["session_id"],
        "strict_budget": merged.get("strict_budget", True),
        "max_results": merged.get("max_results", 3),
    })
    criteria = interpret_local_request(merged)
    # parse_pakistan_intent always provides a language, including for a bare brand.
    # Remember Roman Urdu if the follow-up is purely an English device name.
    if parsed.get("response_language") == "roman_urdu":
        criteria["response_language"] = "roman_urdu"
    elif previous.get("response_language") == "roman_urdu" and not re.search(
        r"\b(?:recommend|show|find|please|best|which)\b", message, re.I
    ):
        criteria["response_language"] = "roman_urdu"
    return criteria


def store_context(criteria):
    preferences = {
        key: value for key in PREFERENCE_FIELDS
        if (value := criteria.get(key)) is not None
    }
    preferences["response_language"] = criteria["response_language"]
    # Stored values are strict JSON, including Decimal as string.
    preferences = json_ready(preferences)
    with transaction.atomic():
        state, _ = ConversationContext.objects.select_for_update().get_or_create(
            session_id=criteria["session_id"], defaults={"preferences": preferences}
        )
        state.preferences = preferences
        state.save(update_fields=["preferences", "updated_at"])


def forget_context(session_id):
    with transaction.atomic():
        context_deleted, _ = ConversationContext.objects.filter(session_id=session_id).delete()
        queries_deleted, _ = RecommendationQuery.objects.filter(session_id=session_id).delete()
    return bool(context_deleted or queries_deleted)
