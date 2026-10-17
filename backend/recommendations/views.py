from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import RecommendationQuery
from .conversation import build_conversation_criteria, previous_context, store_context, forget_context, RESET_PATTERN
from .gemini_research import research_with_gemini
from .gemini_guidance import guidance_configured, generate_general_guidance
from .providers import explain_recommendation
from .serializers import RecommendationRequestSerializer, PakistanRecommendationSerializer, ConversationRequestSerializer
from .local_rank import interpret_local_request, rank_pakistan_phones, local_explanation
from .services import (
    build_criteria,
    json_ready,
    rank_variants,
    serialise_results,
)


class RecommendationView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "recommendations"

    def post(self, request):
        serializer = RecommendationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        criteria = build_criteria(serializer.validated_data)
        ranked_results = rank_variants(criteria)
        results = serialise_results(ranked_results)
        explanation, response_source = explain_recommendation(
            criteria["message"],
            criteria,
            results,
            safety_identifier=str(criteria["session_id"]),
        )
        stored_criteria = json_ready(criteria)
        query = RecommendationQuery.objects.create(
            session_id=criteria["session_id"],
            query_text=criteria["message"][:500],
            country_code=criteria["country_code"],
            currency=criteria["currency"],
            budget=criteria.get("budget"),
            priorities=criteria["priorities"],
            criteria=stored_criteria,
            results=results,
            result_count=len(results),
            response_source=response_source,
        )
        return Response(
            {
                "query_id": str(query.id),
                "criteria": stored_criteria,
                "results": results,
                "explanation": explanation,
                "response_source": response_source,
            }
        )


class HealthView(APIView):
    throttle_classes = []

    def get(self, request):
        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class PakistanLocalRecommendationView(APIView):
    """Pakistan/PKR, database-only suggestions for Patch 06.

    No Gemini requests, web searches or catalog writes occur in this view.
    Response carries an honest research-needed signal for later agent patches.
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "recommendations"

    def post(self, request):
        serializer = PakistanRecommendationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            criteria = interpret_local_request(serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        summary = rank_pakistan_phones(criteria)
        results = summary["results"]
        explanation = local_explanation(criteria, summary)
        data = json_ready(criteria)
        query = RecommendationQuery.objects.create(
            session_id=criteria["session_id"],
            query_text=criteria["message"][:500],
            country_code="PK",
            currency="PKR",
            budget=criteria.get("budget_pkr"),
            priorities=criteria["priorities"],
            criteria=data,
            results=results,
            result_count=len(results),
            response_source="deterministic",
        )
        return Response({
            "query_id": str(query.pk),
            "criteria": data,
            **summary,
            "explanation": explanation,
            "response_source": "deterministic",
            "research_executed": False,
        })


class GeminiGuidanceThrottle(SimpleRateThrottle):
    scope = "gemini_guidance"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class GeminiResearchThrottle(SimpleRateThrottle):
    scope = "gemini_research"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class PakistanConversationView(APIView):
    """Guest bearer-UUID context + DB-first ranking; optional bounded Google Search."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "conversation"

    def post(self, request):
        serializer = ConversationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        use_memory = validated["use_memory"]
        supplied_fields = set(request.data.keys())
        reset = validated["reset_context"] or bool(RESET_PATTERN.search(validated["message"]))
        previous = (previous_context(validated["session_id"])
                    if use_memory and not reset else {})
        try:
            criteria = build_conversation_criteria(validated, supplied_fields, previous)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        summary = rank_pakistan_phones(criteria)
        explanation = local_explanation(criteria, summary)
        if use_memory:
            store_context(criteria)
        research = {"status": "not_requested", "summary": "", "sources": [],
                    "notice": "External research was not requested."}
        if validated["research"]:
            if not summary["needs_research"]:
                research["status"] = "not_needed"
                research["notice"] = "Local evidence is currently sufficient for this shortlist."
            else:
                throttle = GeminiResearchThrottle()
                if not throttle.allow_request(request, self):
                    research["status"] = "rate_limited"
                    research["notice"] = "Research request limit reached; the local shortlist is still available."
                else:
                    research = research_with_gemini(criteria)
        # Gemini is an explicitly requested *ungrounded* advisor when there are
        # no eligible local listings. The separate research flag still controls
        # paid Google Search grounding; neither response becomes catalog data.
        guidance = {"status": "not_requested", "text": "", "notice": "Gemini general guidance was not requested."}
        if validated["guidance"]:
            if summary["results"]:
                guidance = {"status": "not_needed", "text": "", "notice": "Use the eligible local shortlist above."}
            elif research["status"] == "grounded_preview":
                guidance = {"status": "not_needed", "text": "", "notice": "Grounded research was provided separately."}
            elif not guidance_configured():
                guidance = {"status": "disabled", "text": "", "notice": "Gemini general guidance is not configured."}
            elif not GeminiGuidanceThrottle().allow_request(request, self):
                guidance = {"status": "rate_limited", "text": "", "notice": "Gemini guidance limit reached. Local search is still available."}
            else:
                guidance = generate_general_guidance(criteria)
        results = summary["results"]
        # Preserve existing analytics/retention behavior; never store provider output.
        query = RecommendationQuery.objects.create(
            session_id=criteria["session_id"], query_text=criteria["message"][:500],
            country_code="PK", currency="PKR", budget=criteria.get("budget_pkr"),
            priorities=criteria["priorities"], criteria=json_ready(criteria),
            results=results, result_count=len(results), response_source="deterministic",
        )
        return Response({
            "query_id": str(query.pk), "session_id": str(criteria["session_id"]),
            "memory_enabled": use_memory, "memory_used": bool(previous),
            "criteria": json_ready(criteria), **summary, "explanation": explanation,
            "response_source": "deterministic",
            "research_requested": validated["research"],
            "research_executed": research["status"] == "grounded_preview",
            "research": research,
            "guidance_requested": validated["guidance"],
            "guidance": guidance,
        })


class ConversationForgetView(APIView):
    """The UUID is an opaque bearer handle; DELETE is intentionally idempotent."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "conversation"

    def delete(self, request, session_id):
        forget_context(session_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResearchJobCollectionView(APIView):
    """Staff-only, paid research jobs. Public conversational lookup stays read-only."""

    permission_classes = [IsAdminUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "gemini_research"

    def get_throttles(self):
        self.throttle_scope = "gemini_research" if self.request.method == "POST" else "research_job_status"
        return super().get_throttles()

    def post(self, request):
        from django.conf import settings
        from .models import ResearchJob
        from .tasks import run_research_job
        from .serializers import PakistanRecommendationSerializer

        if not (settings.RESEARCH_JOB_QUEUE_ENABLED and settings.GEMINI_WEB_RESEARCH_ENABLED
                and settings.GEMINI_API_KEY):
            return Response({"detail": "Research queue is disabled or not configured."}, status=503)
        serializer = PakistanRecommendationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            criteria = interpret_local_request(serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        # Only bounded structured preferences, never the raw message/session ID.
        allowed = ("budget_pkr", "condition", "grade", "pta_status", "pta_verification",
                   "city", "brand", "priorities", "ram_min", "storage_min")
        stored = json_ready({k: criteria[k] for k in allowed if criteria.get(k) is not None})
        job = ResearchJob.objects.create(criteria=stored, requested_by=request.user)
        try:
            # A non-running Celery worker will leave this queued until it starts.
            run_research_job.apply_async(args=(str(job.id),), retry=False)
        except Exception:
            job.status = ResearchJob.Status.FAILED
            job.notice = "Research could not be queued. Check the worker and broker."
            from django.utils import timezone
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "notice", "finished_at"])
            return Response({"detail": "Research job could not be queued."}, status=503)
        return Response({"id": str(job.id), "status": job.status, "poll_url": f"/api/recommendations/research-jobs/{job.id}/"}, status=202)

    def get(self, request):
        from .models import ResearchJob
        qs = ResearchJob.objects.all() if request.user.is_superuser else ResearchJob.objects.filter(requested_by=request.user)
        return Response({"results": [
            {"id": str(j.id), "status": j.status, "counts": j.counts,
             "notice": j.notice, "created_at": j.created_at.isoformat()}
            for j in qs.order_by("-created_at")[:20]
        ]})


class ResearchJobDetailView(APIView):
    permission_classes = [IsAdminUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "research_job_status"

    def get(self, request, job_id):
        from .models import ResearchJob
        qs = ResearchJob.objects.all() if request.user.is_superuser else ResearchJob.objects.filter(requested_by=request.user)
        job = qs.filter(pk=job_id).first()
        if job is None:
            return Response({"detail": "Not found."}, status=404)
        return Response({"id": str(job.id), "status": job.status, "counts": job.counts,
                         "notice": job.notice, "created_at": job.created_at.isoformat(),
                         "started_at": job.started_at.isoformat() if job.started_at else None,
                         "finished_at": job.finished_at.isoformat() if job.finished_at else None})
