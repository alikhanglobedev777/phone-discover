from django.urls import path

from .views import HealthView, RecommendationView, PakistanLocalRecommendationView

urlpatterns = [
    path("", RecommendationView.as_view(), name="recommendations"),
    path("local/", PakistanLocalRecommendationView.as_view(), name="pakistan-local-recommendations"),
    path("health/", HealthView.as_view(), name="recommendations-health"),
]
