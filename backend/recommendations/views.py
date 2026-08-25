from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import RecommendationQuery
from .providers import explain_recommendation
from .serializers import RecommendationRequestSerializer
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
