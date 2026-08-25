from django.urls import path

from .views import HealthView, RecommendationView

urlpatterns = [
    path("", RecommendationView.as_view(), name="recommendations"),
    path("health/", HealthView.as_view(), name="recommendations-health"),
]
