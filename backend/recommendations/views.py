from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import RecommendationQuery
from .providers import explain_recommendation
from .serializers import RecommendationRequestSerializer, PakistanRecommendationSerializer
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
