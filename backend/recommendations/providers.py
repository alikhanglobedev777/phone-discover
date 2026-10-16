import json
import logging

from django.conf import settings
from openai import OpenAI

from .services import deterministic_explanation, json_ready

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = {"auto", "deterministic", "gemini", "openai"}
SYSTEM_INSTRUCTIONS = (
    "You are a concise phone buying assistant. Use only the supplied candidate facts. "
    "Never invent specifications, prices, sellers, availability, or benchmarks. "
    "For recommendation intent, explain why the first candidate wins and mention one honest "
    "tradeoff. For device_lookup intent, answer only about the supplied exact catalog match. "
    "Keep the answer under 120 words."
)


def get_provider_status() -> dict:
    requested = str(getattr(settings, "AI_PROVIDER", "auto") or "auto").strip().lower()
    if requested not in SUPPORTED_PROVIDERS:
        logger.warning("Unknown AI_PROVIDER '%s'; using deterministic recommendations.", requested)
        return {
            "requested": requested,
            "active": "deterministic",
            "configured": False,
            "model": "built-in ranking engine",
            "label": f"Deterministic fallback (unknown provider: {requested})",
        }

    gemini_key = str(getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    openai_key = str(getattr(settings, "OPENAI_API_KEY", "") or "").strip()

    if requested == "auto":
        if gemini_key:
            active = "gemini"
        elif openai_key:
            active = "openai"
        else:
            active = "deterministic"
    else:
        active = requested

    if active == "gemini" and not gemini_key:
        return {
            "requested": requested,
            "active": "deterministic",
            "configured": False,
            "model": "built-in ranking engine",
            "label": "Deterministic fallback (Gemini key is missing)",
        }
    if active == "openai" and not openai_key:
        return {
            "requested": requested,
            "active": "deterministic",
            "configured": False,
            "model": "built-in ranking engine",
            "label": "Deterministic fallback (OpenAI key is missing)",
        }
    if active == "gemini":
        model = getattr(settings, "GEMINI_CHAT_MODEL", "gemini-3.8-flash")
        return {
            "requested": requested,
            "active": active,
            "configured": True,
            "model": model,
            "label": f"Gemini ({model})",
        }
    if active == "openai":
        model = getattr(settings, "OPENAI_CHAT_MODEL", "gpt-5.6-luna")
        return {
            "requested": requested,
            "active": active,
            "configured": True,
            "model": model,
            "label": f"OpenAI ({model})",
        }
    return {
        "requested": requested,
        "active": "deterministic",
        "configured": True,
        "model": "built-in ranking engine",
        "label": "Deterministic recommendation engine",
    }


def _client_options() -> dict:
    return {
        "timeout": getattr(settings, "AI_REQUEST_TIMEOUT_SECONDS", 15),
        "max_retries": getattr(settings, "AI_MAX_RETRIES", 1),
    }


def _openai_client() -> OpenAI:
    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        **_client_options(),
    )


def _gemini_client() -> OpenAI:
    return OpenAI(
        api_key=settings.GEMINI_API_KEY,
        base_url=getattr(
            settings,
            "GEMINI_OPENAI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
        ),
        **_client_options(),
    )


def _request_payload(message: str, criteria: dict, results: list[dict]) -> str:
    return json.dumps(
        {
            "user_request": message,
            "criteria": json_ready(criteria),
            "candidates": results,
        },
        ensure_ascii=False,
    )


def _explain_with_openai(
    message: str,
    criteria: dict,
    results: list[dict],
    safety_identifier: str,
) -> str:
    request = {
        "model": settings.OPENAI_CHAT_MODEL,
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": _request_payload(message, criteria, results),
        "store": False,
        "max_output_tokens": getattr(settings, "AI_MAX_OUTPUT_TOKENS", 320),
    }
    client = _openai_client()
    try:
        response = client.responses.create(
            **request,
            safety_identifier=safety_identifier,
        )
    except TypeError:
        response = client.responses.create(**request)
    return (response.output_text or "").strip()


def _message_content(response) -> str:
    if not response.choices:
        return ""
    content = response.choices[0].message.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = []
        for part in content:
            text = part.get("text", "") if isinstance(part, dict) else getattr(part, "text", "")
            if text:
                text_parts.append(text)
        return "\n".join(text_parts).strip()
    return ""


def _explain_with_gemini(message: str, criteria: dict, results: list[dict]) -> str:
    response = _gemini_client().chat.completions.create(
        model=settings.GEMINI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": _request_payload(message, criteria, results)},
        ],
        max_tokens=getattr(settings, "AI_MAX_OUTPUT_TOKENS", 320),
    )
    return _message_content(response)


def explain_recommendation(
    message: str,
    criteria: dict,
    results: list[dict],
    safety_identifier: str,
) -> tuple[str, str]:
    fallback = deterministic_explanation(criteria, results)
    status = get_provider_status()
    provider = status["active"]
    if provider == "deterministic" or not results:
        return fallback, "deterministic"

    try:
        if provider == "gemini":
            explanation = _explain_with_gemini(message, criteria, results)
        else:
            explanation = _explain_with_openai(
                message,
                criteria,
                results,
                safety_identifier,
            )
        return explanation or fallback, provider
    except Exception:
        logger.exception(
            "%s recommendation explanation failed; using deterministic fallback.",
            provider.title(),
        )
        return fallback, "deterministic"


def test_provider_connection() -> str:
    status = get_provider_status()
    provider = status["active"]
    if provider == "deterministic":
        return status["label"]
    if provider == "gemini":
        response = _gemini_client().chat.completions.create(
            model=status["model"],
            messages=[{"role": "user", "content": "Reply with exactly AI_PROVIDER_OK"}],
            max_tokens=128,
        )
        if not _message_content(response):
            raise RuntimeError("Gemini returned an empty test response.")
    else:
        response = _openai_client().responses.create(
            model=status["model"],
            input="Reply with exactly AI_PROVIDER_OK",
            store=False,
            max_output_tokens=64,
        )
        if not (response.output_text or "").strip():
            raise RuntimeError("OpenAI returned an empty test response.")
    return f"Connected to {provider.title()} model: {status['model']}"
