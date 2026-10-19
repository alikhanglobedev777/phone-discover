"""Offline tests for the Groq chat adapter; never make a live or billable request."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from .guidance import generate_general_guidance, guidance_configured
from .provider_config import ai_selection, key_for, model_for, public_provider_status, search_selection
from .providers import explain_recommendation, get_provider_status


BASE = dict(
    API_KEY="", API_PROVIDER="auto", AI_MODEL="", AI_PROVIDER="groq",
    GROQ_API_KEY="gsk_unit-test-only", GROQ_MODEL="openai/gpt-oss-20b",
    GEMINI_API_KEY="", OPENAI_API_KEY="", TAVILY_API_KEY="",
    WEB_SEARCH_PROVIDER="auto", GEMINI_WEB_RESEARCH_ENABLED=True,
    WEB_RESEARCH_ENABLED=None, AUTO_WEB_RESEARCH_ENABLED=None,
    GEMINI_AUTO_RESEARCH_ENABLED=False, AI_REQUEST_TIMEOUT_SECONDS=9,
    AI_MAX_RETRIES=0, AI_MAX_OUTPUT_TOKENS=320,
    GEMINI_GUIDANCE_TIMEOUT_SECONDS=12,
)


CANDIDATE = {"device": {"brand": "Example", "name": "One"},
             "variant": {"name": "8/128"}, "strengths": ["Camera"],
             "match_percentage": 83}


def completion(text, *, finish="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(
        finish_reason=finish, message=SimpleNamespace(content=text))])


@override_settings(**BASE)
class GroqProviderTests(SimpleTestCase):
    def test_provider_is_selected_and_status_does_not_expose_secret(self):
        self.assertEqual(ai_selection(), "groq")
        self.assertEqual(model_for("groq"), "openai/gpt-oss-20b")
        self.assertEqual(get_provider_status()["active"], "groq")
        self.assertTrue(guidance_configured())
        self.assertEqual(search_selection(), "groq")
        self.assertNotIn("gsk_unit-test-only", json.dumps(public_provider_status()))

    def test_search_can_use_gemini_independently(self):
        with override_settings(GEMINI_API_KEY="gemini-research-only", WEB_SEARCH_PROVIDER="gemini"):
            self.assertEqual(ai_selection(), "groq")
            self.assertEqual(search_selection(), "gemini")
            self.assertEqual(key_for("gemini"), "gemini-research-only")
            self.assertEqual(key_for("groq"), "gsk_unit-test-only")
        with override_settings(WEB_SEARCH_PROVIDER="groq"):
            self.assertEqual(search_selection(), "groq")

    def test_one_key_mode_auto_detects_groq_without_leaking_to_gemini(self):
        with override_settings(API_KEY="gsk_global-only", API_PROVIDER="auto", GEMINI_API_KEY="unused"):
            self.assertEqual(ai_selection(), "groq")
            self.assertEqual(key_for("groq"), "gsk_global-only")
            self.assertEqual(key_for("gemini"), "")
            self.assertEqual(search_selection(), "groq")
        with override_settings(AI_PROVIDER="auto", GEMINI_API_KEY="gemini"):
            self.assertEqual(ai_selection(), "gemini")  # Existing auto precedence.

    @patch("recommendations.providers.OpenAI")
    def test_legacy_explanation_uses_groq_chat_and_exact_endpoint(self, client_class):
        client = client_class.return_value
        client.chat.completions.create.return_value = completion("Camera wins; battery is weaker.")
        text, origin = explain_recommendation("camera phone", {}, [
            {"name": "Example", "price": "100"}], "session-test")
        self.assertEqual((text, origin), ("Camera wins; battery is weaker.", "groq"))
        self.assertEqual(client_class.call_args.kwargs["api_key"], "gsk_unit-test-only")
        self.assertEqual(client_class.call_args.kwargs["base_url"], "https://api.groq.com/openai/v1")
        payload = client.chat.completions.create.call_args.kwargs
        self.assertEqual(payload["model"], "openai/gpt-oss-20b")
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertNotIn("gsk_unit-test-only", json.dumps(payload))

    @patch("recommendations.providers.OpenAI")
    def test_quota_or_truncated_result_falls_back_to_local(self, client_class):
        client_class.return_value.chat.completions.create.side_effect = RuntimeError("quota")
        text, origin = explain_recommendation("camera phone", {}, [CANDIDATE], "sid")
        self.assertEqual(origin, "deterministic")
        self.assertTrue(text)
        client_class.return_value.chat.completions.create.side_effect = None
        client_class.return_value.chat.completions.create.return_value = completion("bad", finish="length")
        _, origin = explain_recommendation("camera phone", {}, [CANDIDATE], "sid")
        self.assertEqual(origin, "deterministic")

    @patch("recommendations.providers.OpenAI")
    def test_general_guidance_is_sanitized_and_never_used_for_prices(self, client_class):
        client = client_class.return_value
        client.chat.completions.create.return_value = completion(
            "Check camera stabilization and battery. Local prices and PTA are unverified.")
        result = generate_general_guidance({"message": "Recommend a camera phone. Email foo@bar.com "
                                    "and check https://example.org", "priorities": ["camera"]})
        self.assertEqual(result["provider"], "groq")
        self.assertEqual(result["status"], "generated")
        payload = client.chat.completions.create.call_args.kwargs
        self.assertNotIn("foo@bar.com", str(payload))
        self.assertNotIn("https://example.org", str(payload))
        self.assertNotIn("tools", payload)
        client.chat.completions.create.return_value = completion("This costs PKR 100,000")
        rejected = generate_general_guidance({"message": "Tell me the price"})
        self.assertEqual(rejected["status"], "unavailable")

    @patch("recommendations.providers.OpenAI")
    def test_live_management_check_uses_groq_and_not_responses_api(self, client_class):
        client = client_class.return_value
        client.chat.completions.create.return_value = completion("AI_PROVIDER_OK")
        call_command("check_ai_provider", live=True, verbosity=0)
        client.chat.completions.create.assert_called_once()
        client.responses.create.assert_not_called()

    def test_no_key_is_deterministic_and_never_calls_groq(self):
        with override_settings(GROQ_API_KEY=""):
            self.assertEqual(get_provider_status()["active"], "deterministic")
            self.assertFalse(guidance_configured())
            with patch("recommendations.providers.OpenAI") as client_class:
                result = generate_general_guidance({"message": "test"})
                self.assertEqual(result["status"], "disabled")
                client_class.assert_not_called()
