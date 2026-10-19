"""Central capability routing. Keys never appear in public status or cache keys."""

from django.conf import settings

SERVICES = ("gemini", "openai", "groq", "tavily")
AI_SERVICES = ("gemini", "openai", "groq")
SEARCH_SERVICES = ("groq", "tavily", "gemini", "openai")


def global_provider():
    key = str(getattr(settings, "API_KEY", "") or "").strip()
    if not key:
        return None
    explicit = str(getattr(settings, "API_PROVIDER", "auto")).strip().lower()
    if explicit != "auto":
        return explicit if explicit in SERVICES else "unknown"
    if key.startswith("AIza"):
        return "gemini"
    if key.startswith("gsk_"):
        return "groq"
    if key.startswith("sk-"):
        return "openai"
    if key.startswith("tvly-"):
        return "tavily"
    return "unknown"


def key_for(provider):
    selected = global_provider()
    if selected is not None:
        return str(settings.API_KEY).strip() if selected == provider else ""
    return str(getattr(settings, provider.upper() + "_API_KEY", "") or "").strip()


def model_for(provider):
    override = str(getattr(settings, "AI_MODEL", "") or "").strip()
    model_setting = {"gemini": "GEMINI_CHAT_MODEL", "openai": "OPENAI_CHAT_MODEL",
                     "groq": "GROQ_MODEL"}.get(provider, "")
    return (override if override and ai_selection() == provider else "") or getattr(settings, model_setting, "")


def ai_selection():
    global_choice = global_provider()
    if global_choice is not None:
        return global_choice if global_choice in AI_SERVICES else "deterministic"
    requested = str(getattr(settings, "AI_PROVIDER", "auto")).strip().lower()
    if requested == "auto":
        return next((p for p in AI_SERVICES if key_for(p)), "deterministic")
    return requested if requested in AI_SERVICES and key_for(requested) else "deterministic"


def web_enabled():
    explicit = getattr(settings, "WEB_RESEARCH_ENABLED", None)
    return settings.GEMINI_WEB_RESEARCH_ENABLED if explicit is None else explicit


def auto_research_enabled():
    explicit = getattr(settings, "AUTO_WEB_RESEARCH_ENABLED", None)
    return settings.GEMINI_AUTO_RESEARCH_ENABLED if explicit is None else explicit


def search_selection():
    if global_provider() == "unknown":
        return "unavailable"
    requested = str(getattr(settings, "WEB_SEARCH_PROVIDER", "auto")).strip().lower()
    if requested == "auto":
        # Groq GPT-OSS has server-side browser_search; retrieved product pages
        # must still pass source restrictions and the existing import checks.
        return next((p for p in SEARCH_SERVICES if key_for(p)), "source_pages")
    if requested == "source_pages":
        return requested
    return requested if requested in SEARCH_SERVICES and key_for(requested) else "unavailable"


def research_available():
    return bool(web_enabled() and search_selection() != "unavailable")


def public_provider_status():
    return {"ai_provider": ai_selection(), "search_provider": search_selection(),
            "guidance_available": ai_selection() in AI_SERVICES,
            "research_available": research_available(),
            "automatic_research": auto_research_enabled() and research_available(),
            "configuration_error": "Set API_PROVIDER to gemini, openai, groq or tavily for this key."
            if global_provider() == "unknown" else ""}
