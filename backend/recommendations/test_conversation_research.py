"""Patches 07-08: memory isolation, opt-in grounding, fail-closed research."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Brand, Device, DeviceVariant, MarketPriceObservation, ResearchSource, ReviewStatus
from .conversation import build_conversation_criteria, previous_context
from .gemini_research import extract_grounded_answer, research_with_gemini
from .models import ConversationContext, RecommendationQuery
from .serializers import ConversationRequestSerializer


@override_settings(AI_PROVIDER="gemini", GEMINI_API_KEY="test-only", GEMINI_WEB_RESEARCH_ENABLED=False)
class ConversationApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        source = ResearchSource.objects.create(
            url="https://example.org/allowed", title="With rights",
            reuse_status=ResearchSource.ReuseStatus.PERMITTED,
            reuse_notes="Permission to reuse price evidence for local tests.",
        )
        for brand_slug, name, gaming in (("samsung", "Lens", 85), ("orion", "Game", 97)):
            brand = Brand.objects.create(name=brand_slug.title(), slug=brand_slug)
            device = Device.objects.create(brand=brand, name=name, slug=brand_slug + "-example", is_published=True)
            variant = DeviceVariant.objects.create(
                device=device, name="8/128", ram_gb=8, storage_gb=128,
                camera_score=88, gaming_score=gaming, battery_score=75,
                display_refresh_hz=120,
            )
            MarketPriceObservation.objects.create(
                source=source, variant=variant, condition="used", grade="good",
                pta_status="approved", pta_verification="reported", city="Lahore",
                price_min_pkr=Decimal("65000"), price_max_pkr=Decimal("70000"),
                observed_at=timezone.now() - timedelta(hours=1),
                reviewed_at=timezone.now() - timedelta(minutes=20),
                verification_status=ReviewStatus.VERIFIED,
                listing_status="active",
            )

    def setUp(self):
        self.client = APIClient()
        throttle = patch("recommendations.views.PakistanConversationView.throttle_classes", [])
        throttle.start()
        self.addCleanup(throttle.stop)
        researcher = patch("recommendations.views.GeminiResearchThrottle.allow_request", return_value=True)
        researcher.start()
        self.addCleanup(researcher.stop)

    def ask(self, message, **other):
        return self.client.post("/api/recommendations/converse/", {"message": message, **other}, format="json")

    def test_first_turn_returns_session_and_persists_only_preferences(self):
        response = self.ask("Mujhe Lahore mein 80 hazar tak used PTA gaming phone batao", max_results=1)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["memory_used"])
        self.assertEqual(response.data["results"][0]["device"]["slug"], "orion-example")
        state = ConversationContext.objects.get(session_id=response.data["session_id"])
        self.assertEqual(state.preferences["budget_pkr"], "80000")
        self.assertNotIn("message", state.preferences)
        self.assertNotIn("Mujhe", str(state.preferences))
        self.assertFalse(response.data["research_executed"])

    def test_follow_up_brand_keeps_budget_condition_pta_city_and_priorities(self):
        initial = self.ask("Mujhe Lahore mein 80 hazar tak used PTA gaming phone batao", max_results=1)
        follow = self.ask("Samsung mein batao", session_id=initial.data["session_id"])
        self.assertEqual(follow.status_code, 200)
        self.assertTrue(follow.data["memory_used"])
        self.assertEqual(follow.data["criteria"]["budget_pkr"], "80000")
        self.assertEqual(follow.data["criteria"]["condition"], "used")
        self.assertEqual(follow.data["criteria"]["pta_status"], "approved")
        self.assertEqual(follow.data["criteria"]["city"], "Lahore")
        self.assertIn("gaming", follow.data["criteria"]["priorities"])
        self.assertEqual(follow.data["results"][0]["device"]["slug"], "samsung-example")

    def test_exact_iphone_query_survives_follow_up_but_not_other_brand(self):
        first = self.ask("iPhone 18 Pro Max")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["criteria"]["device_query"], "iPhone 18 Pro Max")
        follow = self.ask("used in Lahore", session_id=first.data["session_id"])
        self.assertEqual(follow.data["criteria"]["device_query"], "iPhone 18 Pro Max")
        changed = self.ask("Samsung mein batao", session_id=first.data["session_id"])
        self.assertIsNone(changed.data["criteria"].get("device_query"))
        self.assertEqual(changed.data["criteria"]["brand"], "samsung")

    def test_budget_update_does_not_keep_old_budget(self):
        first = self.ask("used phone under 80k Lahore", max_results=1)
        next_turn = self.ask("budget 90 hazar", session_id=first.data["session_id"])
        self.assertEqual(next_turn.data["criteria"]["budget_pkr"], "90000")
        self.assertEqual(next_turn.data["criteria"]["condition"], "used")

    def test_explicit_filters_override_inferred_and_remembered(self):
        first = self.ask("used PTA gaming under 80k", max_results=1)
        next_turn = self.ask("camera phone", session_id=first.data["session_id"], pta_status="non_pta")
        self.assertEqual(next_turn.data["criteria"]["pta_status"], "non_pta")
        self.assertEqual(next_turn.data["criteria"]["priorities"], ["camera"])
        self.assertEqual(next_turn.data["results"], [])

    def test_different_session_never_receives_prior_preferences(self):
        first = self.ask("used PTA phone under 80k")
        second = self.ask("Samsung mein batao")
        self.assertNotEqual(first.data["session_id"], second.data["session_id"])
        self.assertIsNone(second.data["criteria"]["budget_pkr"])
        self.assertFalse(second.data["memory_used"])

    def test_use_memory_false_does_not_read_or_write_context(self):
        first = self.ask("used phone under 80k")
        uid = first.data["session_id"]
        response = self.ask("Samsung", session_id=uid, use_memory=False)
        self.assertIsNone(response.data["criteria"]["budget_pkr"])
        self.assertEqual(ConversationContext.objects.get(session_id=uid).preferences["budget_pkr"], "80000")

    def test_reset_and_clear_brands(self):
        first = self.ask("Samsung used phone under 80k")
        no_brand = self.ask("any brand gaming phone", session_id=first.data["session_id"])
        self.assertIsNone(no_brand.data["criteria"]["brand"])
        reset = self.ask("gaming", session_id=first.data["session_id"], reset_context=True)
        self.assertIsNone(reset.data["criteria"]["budget_pkr"])
        self.assertIsNone(reset.data["criteria"]["condition"])

    def test_delete_erase_context_and_analytics_idempotently(self):
        first = self.ask("used phone under 80k")
        uid = first.data["session_id"]
        url = "/api/recommendations/conversation/" + uid + "/"
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(ConversationContext.objects.filter(session_id=uid).exists())
        self.assertFalse(RecommendationQuery.objects.filter(session_id=uid).exists())
        new = self.ask("Samsung", session_id=uid)
        self.assertIsNone(new.data["criteria"]["budget_pkr"])

    @override_settings(CONVERSATION_RETENTION_DAYS=7)
    def test_expired_context_is_ignored_then_purged(self):
        first = self.ask("used phone under 80k")
        uid = first.data["session_id"]
        ConversationContext.objects.filter(session_id=uid).update(updated_at=timezone.now() - timedelta(days=8))
        self.assertEqual(previous_context(uid), {})
        second = self.ask("Samsung", session_id=uid, use_memory=False)
        self.assertFalse(second.data["memory_used"])
        out = __import__("io").StringIO()
        call_command("purge_conversation_contexts", stdout=out)
        self.assertIn("Deleted 1", out.getvalue())
        self.assertFalse(ConversationContext.objects.filter(session_id=uid).exists())

    def test_research_is_not_called_by_default(self):
        with patch("recommendations.views.research_with_gemini") as remote:
            result = self.ask("used gaming phone under 20k")
        self.assertEqual(result.status_code, 200)
        remote.assert_not_called()
        self.assertEqual(result.data["research"]["status"], "not_requested")

    def test_opted_in_research_when_local_evidence_insufficient(self):
        mocked = {"status": "grounded_preview", "summary": "Check listings; unverified.",
                  "sources": [{"url": "https://example.org/price", "title": "Price leads"}],
                  "notice": "not verified"}
        with patch("recommendations.views.research_with_gemini", return_value=mocked) as remote:
            response = self.ask("used non PTA phone under 20k", research=True)
        self.assertTrue(response.data["needs_research"])
        self.assertTrue(response.data["research_executed"])
        self.assertEqual(response.data["research"]["sources"], mocked["sources"])
        remote.assert_called_once()
        self.assertEqual(ResearchSource.objects.count(), 1)
        self.assertEqual(MarketPriceObservation.objects.count(), 2)

    def test_not_needed_skips_paid_call(self):
        with patch("recommendations.views.research_with_gemini") as remote:
            response = self.ask("used PTA gaming phone under 80k", max_results=1, research=True)
        self.assertEqual(response.data["research"]["status"], "not_needed")
        remote.assert_not_called()

    def test_provider_not_configured_is_not_claimed_executed(self):
        response = self.ask("used phone under 20k", research=True)
        self.assertEqual(response.data["research"]["status"], "not_configured")
        self.assertFalse(response.data["research_executed"])

    def test_limited_research_returns_local_result_without_calling_provider(self):
        with patch("recommendations.views.GeminiResearchThrottle.allow_request", return_value=False):
            with patch("recommendations.views.research_with_gemini") as remote:
                response = self.ask("used phone under 20k", research=True)
        self.assertEqual(response.data["research"]["status"], "rate_limited")
        remote.assert_not_called()

    def test_ambiguous_new_used_remains_rejected_with_memory(self):
        first = self.ask("used phone under 80k")
        next_turn = self.ask("Compare new and used phones", session_id=first.data["session_id"])
        self.assertEqual(next_turn.status_code, 400)


class ResearchParsingTests(SimpleTestCase):
    @staticmethod
    def answer(uri="https://example.org/phone", text="The price evidence is mixed"):
        return {"candidates": [{
            "finishReason": "STOP", "content": {"parts": [{"text": text}]},
            "groundingMetadata": {"groundingChunks": [{"web": {"uri": uri, "title": "Example"}}]},
        }]}

    def test_citations_needed_to_claim_grounded(self):
        from .gemini_research import ResearchUnavailable
        with self.assertRaises(ResearchUnavailable):
            extract_grounded_answer({"candidates": [{"content": {"parts": [{"text": "Unsourced text"}]}}]})

    def test_unsafe_urls_are_discarded(self):
        from .gemini_research import ResearchUnavailable
        for bad in ("http://example.org/a", "javascript:alert(1)",
                    "https://127.0.0.1/a", "https://localhost/a", "https://x.local/test",
                    "https://user:password@example.org/a"):
            with self.subTest(bad=bad), self.assertRaises(ResearchUnavailable):
                extract_grounded_answer(self.answer(uri=bad))

    def test_research_prompt_targets_canonical_model_not_raw_chat(self):
        from .gemini_research import _prompt
        result = _prompt({"device_query": "iPhone 18 Pro Max", "brand": "apple",
                          "message": "my private raw request"})
        self.assertIn("iPhone 18 Pro Max", result)
        self.assertNotIn("my private raw request", result)

    def test_valid_grounding_is_bounded(self):
        result = extract_grounded_answer(self.answer(text="data" * 1000))
        self.assertEqual(result["status"], "grounded_preview")
        self.assertEqual(len(result["summary"]), 1800)
        self.assertEqual(len(result["sources"]), 1)

    @override_settings(GEMINI_WEB_RESEARCH_ENABLED=True, GEMINI_API_KEY="test-secret", GEMINI_CHAT_MODEL="gemini-3.8-flash")
    def test_gemini_uses_google_search_tool_and_does_not_send_session_or_raw_message(self):
        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, size):
                import json
                return json.dumps(self_answer).encode()

        self_answer = self.answer()
        class FakeOpener:
            def open(self, request, timeout):
                import json
                self_request = json.loads(request.data)
                assert self_request["tools"] == [{"google_search": {}}]
                assert "secret prompt" not in str(self_request)
                assert "session_id" not in str(self_request)
                assert request.get_header("X-goog-api-key") == "test-secret"
                assert timeout <= 20
                return FakeResponse()
        with patch("recommendations.gemini_research.build_opener", return_value=FakeOpener()):
            result = research_with_gemini({"city": "Lahore", "message": "secret prompt", "budget_pkr": Decimal("80000")})
        self.assertEqual(result["status"], "grounded_preview")

    @override_settings(GEMINI_WEB_RESEARCH_ENABLED=True, GEMINI_API_KEY="test-secret")
    def test_provider_failure_has_no_error_or_secret_leak(self):
        class FailingOpener:
            def open(self, request, timeout):
                raise OSError("test-secret in error")
        with patch("recommendations.gemini_research.build_opener", return_value=FailingOpener()):
            result = research_with_gemini({"city": "Lahore"})
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("test-secret", str(result))
