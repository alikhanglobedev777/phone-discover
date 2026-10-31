from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from django.conf import settings
from django.db.models import Q
import re
from django.utils.text import slugify
from rest_framework import serializers

from catalog.models import Device

from .models import RecommendationQuery
from .conversation import build_conversation_criteria, previous_context, store_context, forget_context, RESET_PATTERN
from .provider_config import research_available as research_configured, auto_research_enabled
from .automatic_research import research_and_save, cached_research
from .guidance import guidance_configured, generate_general_guidance
from .providers import explain_recommendation
from .serializers import RecommendationRequestSerializer, PakistanRecommendationSerializer, ConversationRequestSerializer
from .local_rank import interpret_local_request, rank_pakistan_phones, local_explanation, price_reference_alternatives
from .local_intent import parse_pakistan_intent
from .model_identity import matches_phone_model
from .catalog_details import exact_catalog_details, catalog_details_for_slugs
from .catalog_advisor import catalog_mentions, specs_recommendations, compare_catalog_phones
from .services import (
    build_criteria,
    json_ready,
    rank_variants,
    serialise_results,
)


class ComparisonLookupSerializer(serializers.Serializer):
    query = serializers.CharField(min_length=3, max_length=100, trim_whitespace=True)


class ComparisonPhoneLookupView(APIView):
    """Public, rate-limited exact-model lookup; research only on a local miss."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "conversation"

    def post(self, request):
        serializer = ComparisonLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested = serializer.validated_data["query"]
        parsed = parse_pakistan_intent(requested)
        brand = parsed.get("brand")
        model_query = parsed.get("device_query") or requested

        def rows(devices):
            return [{"slug": d.slug, "name": d.name, "brand": d.brand.name,
                     "primary_image_url": d.primary_image_url, "data_source": d.data_source}
                    for d in devices if matches_phone_model(requested, d.brand.name, d.name)]

        # Use canonical names for local discovery; a bare "S24 Ultra" should
        # locate the existing "Galaxy S24 Ultra" instead of wasting a web call.
        local = Device.objects.filter(is_published=True).select_related("brand")
        if brand:
            local = local.filter(brand__slug__iexact=brand)
        local = local.filter(
            Q(name__icontains=model_query) | Q(slug__icontains=slugify(model_query))
        )[:20]
        matches = rows(local)
        if matches:
            return Response({"status": "found_local", "devices": matches,
                             "notice": "This exact phone is already in the catalog.", "sources": []})
        if not research_configured():
            return Response({"status": "unavailable", "devices": [], "sources": [],
                             "notice": "Web research is not configured. Please try another phone."})
        if not GeminiResearchThrottle().allow_request(request, self):
            return Response({"status": "rate_limited", "devices": [], "sources": [],
                             "notice": "Research limit reached. Please try again later."}, status=429)
        import uuid
        criteria = interpret_local_request({"message": requested, "session_id": uuid.uuid4(),
                                            "strict_budget": True, "max_results": 5})
        criteria["device_query"] = model_query
        criteria["comparison_target"] = requested
        research = research_and_save(criteria)
        # Use the importer-returned slugs, not ranking cards. Ranking uses
        # price evidence and can yield [] after a successful DB import.
        slugs = research.get("saved_device_slugs", [])
        candidates = Device.objects.filter(is_published=True, slug__in=slugs).select_related("brand")
        matched = rows(candidates)
        return Response({"status": "researched" if matched else research.get("status", "not_found"),
                         "devices": matched, "sources": research.get("sources", []),
                         "saved": research.get("saved", {}),
                         "notice": ("Source-backed information for this exact phone was saved. "
                                    "Review reported specifications and prices before buying."
                                    if matched else research.get("notice") or
                                    "No verifiable exact-model product and price evidence was found.")})


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

        # Resolve names against the PUBLISHED catalog before asking an AI.
        # Longest model tokens win (S26 Ultra is never plain S26).
        mentions = catalog_mentions(validated["message"])
        comparison_requested = bool(re.search(
            r"\b(?:compare|comparison|versus|vs|which\s+(?:one|phone)\s+.*better|"
            r"better\s+(?:camera|battery|gaming)\s+between)\b",
            validated["message"], re.I,
        ))
        previous_slugs = previous.get("recent_device_slugs", [])
        if not isinstance(previous_slugs, list):
            previous_slugs = []
        comparison_slugs = []
        if comparison_requested:
            if len(mentions) >= 2:
                comparison_slugs = [m["slug"] for m in mentions[:2]]
            elif mentions and previous_slugs:
                comparison_slugs = [previous_slugs[0], mentions[0]["slug"]]
            elif len(previous_slugs) >= 2:
                comparison_slugs = previous_slugs[:2]
        comparison = compare_catalog_phones(comparison_slugs, criteria["priorities"])
        if mentions and comparison is None:
            criteria["device_query"] = mentions[0]["name"]
            criteria["brand"] = mentions[0]["brand"]
        elif not mentions and not comparison_requested and re.search(
            r"\b(?:best|recommend|suggest|top)\b", validated["message"], re.I
        ) and not re.search(r"\b(?:about|details|specs)\b", validated["message"], re.I):
            # A new category recommendation must not remain stuck on an older
            # exact phone. Other explicit conditions/budget can carry forward.
            criteria["device_query"] = None

        if comparison:
            summary = {"results": [], "count": 0, "needs_research": False,
                       "research_reason": None, "coverage_incomplete": False}
            catalog_details = catalog_details_for_slugs(
                [phone["slug"] for phone in comparison["phones"]]
            )
            explanation = (
                "Here is a local catalog comparison. A score only establishes an "
                "editorial ordering where both phones have comparable data; "
                "otherwise no winner is claimed."
            )
        else:
            summary = rank_pakistan_phones(criteria)
            catalog_details = exact_catalog_details(criteria)
            explanation = local_explanation(criteria, summary)
        specs_results = []
        if (not comparison and not catalog_details and not criteria.get("device_query")
                and criteria["priorities"]):
            # Keep price-evidenced cards first, then fill any remaining spaces
            # with explicitly UNPRICED catalog suggestions. Never mix the
            # evidence types or silently treat specs as a market offer.
            remaining = max(0, criteria["max_results"] - len(summary["results"]))
            if remaining:
                specs_results = specs_recommendations(
                    {**criteria, "max_results": remaining},
                    exclude_slugs=[item["device"]["slug"] for item in summary["results"]],
                )
        if specs_results and not summary["results"]:
            dims = ", ".join(criteria["priorities"])
            explanation = (
                f"I found {len(specs_results)} published catalog candidates for "
                f"{dims}. These are specifications-based suggestions, ordered using "
                "available editorial scores (not independent benchmarks). "
                "Their Pakistani price, budget fit, PTA status and city availability "
                "are not verified for your filters; use the details links to inspect facts."
            )
        elif specs_results:
            explanation += (
                " Other phones are shown separately as specs-only candidates; "
                "their price, PTA, condition and city eligibility is not verified."
            )
        if not comparison and criteria.get("device_query") and not catalog_details and not summary["results"]:
            # Never fall back to a sibling (e.g. S26 when S26 Ultra is requested).
            explanation = (
                f"I could not find an exact published local catalog match for "
                f"{criteria['device_query']}. I will not substitute a different model."
            )
        if catalog_details and not comparison and not summary["results"]:
            phone = catalog_details[0]
            explanation = (
                f"{phone['brand']} {phone['name']} is in the local catalog. "
                "Its saved specifications are below. A verified matching Pakistan "
                "price is not available for the selected filters."
            )
        alternatives = (price_reference_alternatives(criteria, summary) if not comparison
                        else {"results": [], "unconfirmed_filters": [], "notice": ""})
        if alternatives["results"]:
            explanation = (
                "Aap ke city/PTA filters ke liye exact evidence nahi mila. Neeche source-linked price references dekh sakte hain."
                if criteria["response_language"] == "roman_urdu" else
                "I could not confirm an exact match for your city/PTA filters. Here are source-linked price references to compare."
            )
        research = {"status": "not_requested", "summary": "", "sources": [],
                    "notice": "External research was not requested."}
        automatic = bool(auto_research_enabled() and research_configured() and
                         not summary["results"] and not catalog_details and
                         not specs_results and not comparison)
        if validated["research"] or automatic:
            if comparison:
                research["status"] = "not_needed"
                research["notice"] = "The two local catalog phones are compared without external research."
            elif catalog_details and not summary["results"]:
                research["status"] = "not_needed"
                research["notice"] = "The exact phone is already in the local catalog; its specifications are shown below."
            elif not summary["needs_research"]:
                research["status"] = "not_needed"
                research["notice"] = "Local evidence is currently sufficient for this shortlist."
            else:
                throttle = GeminiResearchThrottle()
                cached = cached_research(criteria)
                if cached is None and not throttle.allow_request(request, self):
                    research["status"] = "rate_limited"
                    research["notice"] = "Research request limit reached; the local shortlist is still available."
                else:
                    research = cached if cached is not None else research_and_save(criteria)
                    if research.get("catalog_updated"):
                        summary = rank_pakistan_phones(criteria)
                        alternatives = price_reference_alternatives(criteria, summary)
                        explanation = local_explanation(criteria, summary)
                        if not summary["results"] and research.get("results"):
                            explanation = (
                                "Internet par sourced phones mile aur catalog mein save ho gaye. City/PTA ki jo details confirm nahi, cards mein wazeh hain."
                                if criteria["response_language"] == "roman_urdu" else
                                "I found phones online and saved the sourced details to the catalog. See the web-researched cards; city/PTA claims remain source-reported or unknown."
                            )
        # General guidance is a separate opt-in AI capability, not price evidence.
        guidance = {"status": "not_requested", "text": "", "notice": "AI general guidance was not requested."}
        if validated["guidance"]:
            if comparison or catalog_details or specs_results:
                guidance = {"status": "not_needed", "text": "",
                            "notice": "Published local catalog information is shown above."}
            elif summary["results"]:
                guidance = {"status": "not_needed", "text": "", "notice": "Use the eligible local shortlist above."}
            elif research["status"] == "grounded_preview":
                guidance = {"status": "not_needed", "text": "", "notice": "Grounded research was provided separately."}
            elif not guidance_configured():
                guidance = {"status": "disabled", "text": "", "notice": "AI general guidance is not configured."}
            elif not GeminiGuidanceThrottle().allow_request(request, self):
                guidance = {"status": "rate_limited", "text": "", "notice": "AI guidance limit reached. Local search is still available."}
            else:
                guidance = generate_general_guidance(criteria)
        results = summary["results"]
        if use_memory:
            displayed_slugs = (
                [phone["slug"] for phone in comparison["phones"]] if comparison else
                [phone["slug"] for phone in catalog_details] or
                [row["device"]["slug"] for row in results] or
                [phone["slug"] for phone in specs_results] or
                previous_slugs
            )
            store_context(criteria, recent_device_slugs=displayed_slugs)
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
            "price_references": alternatives,
            "catalog_details": catalog_details,
            "specs_results": specs_results,
            "comparison": comparison,
            "response_source": "deterministic",
            "research_requested": validated["research"],
            "research_automatic": automatic,
            "catalog_updated": research.get("catalog_updated", False),
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

        if not (settings.RESEARCH_JOB_QUEUE_ENABLED and research_configured()):
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
