from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import RecommendationQuery


@override_settings(AI_PROVIDER="deterministic", GEMINI_API_KEY="", OPENAI_API_KEY="")
class RecommendationApiTests(TestCase):
    def setUp(self):
        call_command("seed_demo", verbosity=0)
        self.client = APIClient()
        # These functional tests exercise recommendations, not rate limiting.
        # Avoid sharing the per-IP throttle counter with other test classes.
        throttle_patch = patch("recommendations.views.RecommendationView.throttle_classes", [])
        throttle_patch.start()
        self.addCleanup(throttle_patch.stop)

    def test_natural_language_recommendations_respect_budget(self):
        response = self.client.post(
            "/api/recommendations/",
            {"message": "Best gaming phone under $500", "country_code": "US"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["device"]["slug"], "atlas-play-5g")
        self.assertTrue(
            all(float(result["offer"]["price"]) <= 500 for result in response.data["results"])
        )

    def test_structured_priorities_return_explainable_results(self):
        response = self.client.post(
            "/api/recommendations/",
            {
                "message": "Photography matters most",
                "budget": "800",
                "priorities": ["camera"],
                "country_code": "US",
                "currency": "USD",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        result = response.data["results"][0]
        self.assertTrue(result["recommended"])
        self.assertIn("match_percentage", result)
        self.assertTrue(result["strengths"])
        self.assertIn("tradeoffs", result)

    def test_brand_exclusions_are_applied(self):
        response = self.client.post(
            "/api/recommendations/",
            {
                "message": "Best value phone",
                "excluded_brands": ["Atlas"],
                "strict_budget": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "Atlas",
            [result["device"]["brand"] for result in response.data["results"]],
        )

    def test_query_is_saved_for_anonymous_admin_analytics(self):
        response = self.client.post(
            "/api/recommendations/",
            {"message": "Long battery life under $700"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        query = RecommendationQuery.objects.get(id=response.data["query_id"])
        self.assertEqual(query.result_count, len(response.data["results"]))
        self.assertEqual(query.response_source, "deterministic")
        self.assertIn("battery", query.priorities)

    def test_conflicting_brand_preferences_are_rejected(self):
        response = self.client.post(
            "/api/recommendations/",
            {
                "message": "Recommend a phone",
                "preferred_brands": ["Nova"],
                "excluded_brands": ["nova"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_no_exact_match_returns_helpful_empty_state(self):
        response = self.client.post(
            "/api/recommendations/",
            {
                "message": "Any phone under one dollar",
                "budget": "1",
                "currency": "USD",
                "strict_budget": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])
        self.assertIn("could not find an exact catalog match", response.data["explanation"])

    def test_old_analytics_can_be_purged(self):
        self.client.post(
            "/api/recommendations/",
            {"message": "Best camera phone"},
            format="json",
        )
        RecommendationQuery.objects.update(created_at=timezone.now() - timedelta(days=120))
        call_command("purge_recommendation_queries", days=90, verbosity=0)
        self.assertFalse(RecommendationQuery.objects.exists())

    def test_exact_device_lookup_ignores_recommendation_budget_filters(self):
        response = self.client.post(
            "/api/recommendations/",
            {
                "message": "Tell me about Google Pixel 7a",
                "budget": "1",
                "currency": "USD",
                "strict_budget": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["criteria"]["intent"], "device_lookup")
        self.assertEqual(response.data["results"][0]["device"]["slug"], "google-pixel-7a")
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIn("found Google Pixel 7a", response.data["explanation"])

    def test_unknown_device_lookup_does_not_return_unrelated_phones(self):
        response = self.client.post(
            "/api/recommendations/",
            {
                "message": "Samsung Galaxy S99",
                "budget": "500",
                "currency": "USD",
                "strict_budget": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["criteria"]["intent"], "device_lookup")
        self.assertEqual(response.data["criteria"]["device_query"], "Samsung Galaxy S99")
        self.assertEqual(response.data["results"], [])
        self.assertEqual(response.data["response_source"], "deterministic")
        self.assertIn("not find 'Samsung Galaxy S99'", response.data["explanation"])

    @override_settings(
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="test-gemini-key",
        GEMINI_CHAT_MODEL="gemini-test-model",
        GEMINI_OPENAI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/",
        AI_REQUEST_TIMEOUT_SECONDS=7,
        AI_MAX_RETRIES=0,
        AI_MAX_OUTPUT_TOKENS=240,
    )
    @patch("recommendations.providers.OpenAI")
    def test_gemini_explanation_is_used_when_configured(self, openai_client_class):
        completion = Mock()
        completion.choices = [Mock(message=Mock(content="Gemini selected the strongest match."))]
        client = openai_client_class.return_value
        client.chat.completions.create.return_value = completion

        response = self.client.post(
            "/api/recommendations/",
            {"message": "Best camera phone under $800", "country_code": "US"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["response_source"], "gemini")
        self.assertEqual(response.data["explanation"], "Gemini selected the strongest match.")
        openai_client_class.assert_called_once_with(
            api_key="test-gemini-key",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            timeout=7,
            max_retries=0,
        )
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "gemini-test-model")
        self.assertNotIn("test-gemini-key", str(request))

    @override_settings(
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="test-gemini-key",
        GEMINI_CHAT_MODEL="gemini-test-model",
    )
    @patch("recommendations.providers.OpenAI")
    def test_gemini_error_uses_deterministic_fallback(self, openai_client_class):
        openai_client_class.return_value.chat.completions.create.side_effect = RuntimeError(
            "free quota exhausted"
        )

        response = self.client.post(
            "/api/recommendations/",
            {"message": "Best gaming phone under $500", "country_code": "US"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["response_source"], "deterministic")
        self.assertIn("strongest match", response.data["explanation"])
        query = RecommendationQuery.objects.get(id=response.data["query_id"])
        self.assertEqual(query.response_source, "deterministic")

    @override_settings(
        AI_PROVIDER="gemini",
        GEMINI_API_KEY="test-gemini-key",
        GEMINI_CHAT_MODEL="gemini-test-model",
    )
    @patch("recommendations.providers.OpenAI")
    def test_live_provider_check_generates_text_instead_of_only_reading_metadata(
        self,
        openai_client_class,
    ):
        completion = Mock()
        completion.choices = [Mock(message=Mock(content="AI_PROVIDER_OK"))]
        client = openai_client_class.return_value
        client.chat.completions.create.return_value = completion

        call_command("check_ai_provider", live=True, verbosity=0)

        client.chat.completions.create.assert_called_once()
        client.models.retrieve.assert_not_called()
