"""Local-first fallback: cache searches, save sourced phones, then rank again."""

import hashlib
import json
import re

from django.utils.text import slugify

from django.core.cache import cache
from django.conf import settings

from catalog.web_import import import_web_phones
from .research_providers import research_catalog
from .provider_config import search_selection, key_for, model_for
from .local_rank import rank_pakistan_phones


def _cache_key(criteria):
    allowed = ("budget_pkr", "condition", "grade", "pta_status", "pta_verification", "city",
               "brand", "device_query", "priorities", "ram_min", "storage_min", "strict_budget", "comparison_target")
    return "catalog-research:" + hashlib.sha256(json.dumps(
        {"criteria": {k: criteria.get(k) for k in allowed}, "provider": search_selection(),
         "credential_version": hashlib.sha256(key_for(search_selection()).encode()).hexdigest(),
         "model": (settings.GROQ_WEB_MODEL if search_selection() == "groq" else model_for(search_selection()))
         if search_selection() in ("gemini", "openai", "groq") else "",
         "sources": list(settings.GEMINI_RESEARCH_SOURCE_DOMAINS)},
        default=str, sort_keys=True,
    ).encode()).hexdigest()


def cached_research(criteria):
    cached = cache.get(_cache_key(criteria))
    if cached is not None:
        slugs = cached.get("_slugs", [])
        result = {k: v for k, v in cached.items() if k != "_slugs"}
        # Revalidate visibility, source decisions and freshness without writes.
        result["results"] = _research_cards(criteria, slugs) if slugs else []
        return {**result, "cached": True, "catalog_updated": False}
    return None


def _research_cards(criteria, slugs):
    reference = {**criteria, "device_slugs": slugs, "city": None, "pta_verification": None}
    if reference.get("pta_status") == "approved":
        reference["pta_status"] = None
    cards = rank_pakistan_phones(reference)["results"]
    for card in cards:
        card["recommended"] = False
    return cards


def _matches_comparison_target(phone, query):
    """Only import results for the model requested by the comparison visitor.

    Optional memory-size suffixes are ignored for identity; the import still
    validates the exact RAM/storage variant and the original cited source.
    """
    words = re.sub(r"\b\d+\s*(?:gb|tb)\b", "", query, flags=re.I)
    words = re.sub(r"\b(?:mobile|phone|pakistan)\b", "", words, flags=re.I)
    wanted = slugify(words)
    brand = str(phone.get("brand", "")).strip()
    name = str(phone.get("name", "")).strip()
    if name.casefold().startswith(brand.casefold() + " "):
        name = name[len(brand):].strip()
    found = slugify(f"{brand} {name}")
    # Only exact model identity, not 'A57' as a match for 'A57 Pro'.
    return bool(wanted and len(wanted.split("-")) >= 2 and
                (wanted == found or found.endswith("-" + wanted)))


def research_and_save(criteria):
    key = _cache_key(criteria)
    cached = cached_research(criteria)
    if cached is not None:
        return cached
    if not cache.add(key + ":busy", True, timeout=120):
        return {"status": "in_progress", "summary": "", "sources": [], "results": [], "saved": {},
                "notice": "A matching web search is already running. Please retry shortly."}
    try:
        research = research_catalog(criteria)
        if criteria.get("comparison_target") and research.get("status") == "grounded_preview":
            document = research.get("document") or {}
            if isinstance(document, dict):
                phones = document.get("phones", [])
                research["document"] = {**document, "phones": [
                    phone for phone in (phones if isinstance(phones, list) else [])
                    if isinstance(phone, dict) and _matches_comparison_target(phone, criteria["comparison_target"])
                ]}
        stats, slugs = import_web_phones(research)
        research.pop("document", None)
        research["saved"] = stats
        research["catalog_updated"] = bool(stats["prices_saved"])
        if slugs:
            # Saved discoveries may be useful references even when a source does
            # not establish the requested city/independently checked PTA status.
            research["results"] = _research_cards(criteria, slugs)
            research["summary"] = f"Saved {stats['devices_created']} new phones and {stats['prices_saved']} sourced price records to the catalog."
        elif research["status"] == "grounded_preview":
            research["summary"] = "Search completed, but no cited phone/variant prices passed import checks."
        research["cached"] = False
        cache.set(key, {**research, "_slugs": slugs}, timeout=600 if slugs else 60)
        return research
    finally:
        cache.delete(key + ":busy")
