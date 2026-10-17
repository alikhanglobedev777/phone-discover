"""Patch 13: ungrounded Gemini is opt-in and never a price source."""

import json
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from .gemini_guidance import _extract_response, _public_question, generate_general_guidance
from .models import RecommendationQuery


GOOD = {"candidates": [{
    "finishReason": "STOP",
    "content": {"parts": [{"text": "For gaming, check thermal behavior and long-term software support. Exact Pakistani prices and PTA status are not verified."}]},
}]}


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return json.dumps(self.payload).encode("utf-8")


@override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="test-only", GEMINI_CHAT_MODEL="gemini-3.8-flash")
class GuidanceServiceTests(SimpleTestCase):
    def test_sends_one_ungrounded_request_with_low_thinking_and_no_history(self):
        received = {}

        class FakeOpener:
            def open(self, request, timeout):
                received["request"] = request
                received["timeout"] = timeout
                return FakeResponse(GOOD)

        criteria = {"message": "What about iPhone 18 Pro Max? contact a@b.com at +923001234567 https://x.test", "device_query": "iPhone 18 Pro Max", "priorities": ["gaming"], "session_id": "PRIVATE-SESSION-ID"}
        with patch("recommendations.gemini_guidance.build_opener", return_value=FakeOpener()):
            result = generate_general_guidance(criteria)
        self.assertEqual(result["status"], "generated")
        self.assertIn("not web-verified", result["notice"])
        sent = json.loads(received["request"].data)
        self.assertNotIn("google_search", str(sent))
        self.assertNotIn("tools", sent)
        self.assertEqual(sent["generationConfig"]["thinkingConfig"], {"thinkingLevel": "low"})
        self.assertGreaterEqual(sent["generationConfig"]["maxOutputTokens"], 2048)
        self.assertLessEqual(received["timeout"], 45)
        self.assertEqual(received["request"].get_header("X-goog-api-key"), "test-only")
        self.assertNotIn("PRIVATE-SESSION-ID", str(sent))
        self.assertNotIn("a@b.com", str(sent))
        self.assertNotIn("+923001234567", str(sent))
        self.assertNotIn("https://x.test", str(sent))

    def test_no_provider_call_when_disabled(self):
        with override_settings(AI_PROVIDER="deterministic"), patch("recommendations.gemini_guidance.build_opener") as opener:
            result = generate_general_guidance({"message": "Hello"})
        opener.assert_not_called()
        self.assertEqual(result["status"], "disabled")

    def test_provider_error_fails_closed_and_does_not_leak_key(self):
        class BrokenOpener:
            def open(self, request, timeout):
                raise OSError("test-only secret")

        with patch("recommendations.gemini_guidance.build_opener", return_value=BrokenOpener()):
            result = generate_general_guidance({"message": "camera phone"})
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("test-only", str(result))

    def test_rejects_incomplete_invented_price_and_unsupported_citation(self):
        for item in (
            {"candidates": [{"finishReason": "MAX_TOKENS", "content": GOOD["candidates"][0]["content"]}]},
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "It costs PKR 120000 in Lahore"}]}}]},
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "It costs $499"}]}}]},
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "See https://wrong.example/offer"}]}}]},
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": ""}]}}]},
            {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "A" * 3100}]}}]},
        ):
            with self.subTest(item=item), self.assertRaises(ValueError):
                _extract_response(item)

    def test_plain_response_truncated_and_redaction_bounded(self):
        self.assertIn("[email omitted]", _public_question("email test@example.org"))
        self.assertLessEqual(len(_public_question("a" * 1000)), 500)
        self.assertLessEqual(len(_extract_response({"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "Hello " * 260}]}}]})), 1500)


@override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="test-only", GEMINI_WEB_RESEARCH_ENABLED=False)
class GuidanceConversationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        conversation_throttle = patch("recommendations.views.PakistanConversationView.throttle_classes", [])
        conversation_throttle.start()
        self.addCleanup(conversation_throttle.stop)
        guidance_throttle = patch("recommendations.views.GeminiGuidanceThrottle.allow_request", return_value=True)
        guidance_throttle.start()
        self.addCleanup(guidance_throttle.stop)

    def ask(self, **fields):
        return self.client.post("/api/recommendations/converse/", {"message": "Tell me about iPhone 18 Pro Max", **fields}, format="json")

    def test_no_opt_in_never_calls_google(self):
        with patch("recommendations.views.generate_general_guidance") as remote:
            result = self.ask()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["guidance"]["status"], "not_requested")
        remote.assert_not_called()

    def test_explicit_guidance_no_results_and_not_persisted(self):
        mock_result = {"status": "generated", "text": "AI SAMPLE TEXT", "notice": "Not verified."}
        with patch("recommendations.views.generate_general_guidance", return_value=mock_result) as remote:
            result = self.ask(guidance=True)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["results"], [])
        self.assertTrue(result.data["needs_research"])
        self.assertEqual(result.data["guidance"], mock_result)
        self.assertEqual(result.data["response_source"], "deterministic")
        self.assertFalse(result.data["research_executed"])
        remote.assert_called_once()
        self.assertEqual(RecommendationQuery.objects.count(), 1)
        self.assertNotIn("AI SAMPLE TEXT", str(RecommendationQuery.objects.first().criteria))
        self.assertNotIn("AI SAMPLE TEXT", str(RecommendationQuery.objects.first().results))

    def test_rate_limit_is_specific_to_guidance(self):
        with patch("recommendations.views.GeminiGuidanceThrottle.allow_request", return_value=False), patch("recommendations.views.generate_general_guidance") as remote:
            result = self.ask(guidance=True)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["guidance"]["status"], "rate_limited")
        remote.assert_not_called()

    def test_grounded_research_skips_duplicate_guidance_call(self):
        research = {"status": "grounded_preview", "summary": "Unverified price leads.", "sources": [{"url": "https://example.org/a", "title": "Source"}], "notice": "unverified"}
        with patch("recommendations.views.research_with_gemini", return_value=research), patch("recommendations.views.GeminiResearchThrottle.allow_request", return_value=True), patch("recommendations.views.generate_general_guidance") as remote:
            result = self.ask(research=True, guidance=True)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["guidance"]["status"], "not_needed")
        remote.assert_not_called()

    def test_disabled_provider_keeps_local_response(self):
        with override_settings(AI_PROVIDER="deterministic"), patch("recommendations.views.generate_general_guidance") as remote:
            result = self.ask(guidance=True)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["guidance"]["status"], "disabled")
        remote.assert_not_called()
