"""Regression tests for Groq browser-search denial and safe failover."""

from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from django.test import SimpleTestCase, override_settings

from .research_providers import research_catalog, research_with_groq


@override_settings(
    AI_PROVIDER="groq", API_PROVIDER="auto", API_KEY="",
    GROQ_API_KEY="gsk_test", TAVILY_API_KEY="tvly_test",
    WEB_SEARCH_PROVIDER="groq", WEB_RESEARCH_ENABLED=True,
)
class GroqBrowserFailoverTests(SimpleTestCase):
    @patch("recommendations.research_providers.research_source_pages")
    @patch("recommendations.research_providers.research_with_tavily")
    @patch("recommendations.research_providers.research_with_groq")
    def test_access_denied_uses_sourced_tavily_result(self, groq, tavily, source_pages):
        groq.return_value = {"status": "access_denied", "provider": "groq"}
        tavily.return_value = {
            "status": "grounded_preview", "provider": "tavily",
            "sources": [{"url": "https://www.whatmobile.com.pk/Samsung_Galaxy-A57"}],
            "document": {"phones": []},
        }
        result = research_catalog({"device_query": "Samsung Galaxy A57"})
        self.assertEqual(result["provider"], "tavily")
        self.assertEqual(result["fallback_from"], "groq")
        self.assertEqual(result["provider_status"], "access_denied")
        self.assertEqual(result["status"], "grounded_preview")
        tavily.assert_called_once()
        source_pages.assert_not_called()

    @patch("recommendations.research_providers.research_source_pages")
    @patch("recommendations.research_providers.research_with_tavily")
    @patch("recommendations.research_providers.research_with_groq")
    def test_if_tavily_cannot_verify_it_tries_source_pages(self, groq, tavily, source_pages):
        groq.return_value = {"status": "access_denied", "provider": "groq"}
        tavily.return_value = {"status": "no_sources", "provider": "tavily"}
        source_pages.return_value = {"status": "grounded_preview", "provider": "source_pages"}
        result = research_catalog({"device_query": "Samsung Galaxy A57"})
        self.assertEqual(result["fallback_from"], "groq")
        self.assertEqual(result["provider"], "source_pages")
        source_pages.assert_called_once()

    @patch("recommendations.research_providers.research_source_pages")
    @patch("recommendations.research_providers.research_with_tavily")
    @patch("recommendations.research_providers.research_with_groq")
    def test_successful_groq_does_not_invoke_fallbacks(self, groq, tavily, source_pages):
        groq.return_value = {"status": "grounded_preview", "provider": "groq"}
        result = research_catalog({"device_query": "Samsung Galaxy A57"})
        self.assertEqual(result["provider"], "groq")
        tavily.assert_not_called()
        source_pages.assert_not_called()

    @override_settings(TAVILY_API_KEY="")
    @patch("recommendations.research_providers.research_source_pages")
    @patch("recommendations.research_providers.research_with_tavily")
    @patch("recommendations.research_providers.research_with_groq")
    def test_no_tavily_key_keeps_existing_source_fallback(self, groq, tavily, source_pages):
        groq.return_value = {"status": "access_denied", "provider": "groq"}
        source_pages.return_value = {"status": "grounded_preview", "provider": "source_pages"}
        result = research_catalog({"device_query": "Samsung Galaxy A57"})
        self.assertEqual(result["provider"], "source_pages")
        tavily.assert_not_called()

    @patch("recommendations.research_providers.build_opener")
    def test_groq_403_logs_only_safe_error_code(self, opener):
        opener.return_value.open.side_effect = HTTPError(
            "https://api.groq.com/openai/v1/chat/completions", 403, "Forbidden", {},
            BytesIO(b'{"error":{"code":"model_permission_blocked_project",'
                    b'"message":"do not log this message"}}'),
        )
        with self.assertLogs("recommendations.research_providers", level="WARNING") as logs:
            result = research_with_groq({"device_query": "Samsung Galaxy A57"})
        self.assertEqual(result["status"], "access_denied")
        self.assertIn("code=model_permission_blocked_project", logs.output[0])
        self.assertNotIn("do not log this message", logs.output[0])
