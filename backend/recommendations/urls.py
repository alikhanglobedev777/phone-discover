from django.urls import path

from .views import ComparisonPhoneLookupView, ResearchJobCollectionView, ResearchJobDetailView, HealthView, RecommendationView, PakistanLocalRecommendationView, PakistanConversationView, ConversationForgetView

urlpatterns = [
    path("", RecommendationView.as_view(), name="recommendations"),
    path("compare-lookup/", ComparisonPhoneLookupView.as_view(), name="comparison-phone-lookup"),
    path("local/", PakistanLocalRecommendationView.as_view(), name="pakistan-local-recommendations"),
    path("converse/", PakistanConversationView.as_view(), name="pakistan-converse"),
    path("conversation/<uuid:session_id>/", ConversationForgetView.as_view(), name="forget-conversation"),
    path("research-jobs/", ResearchJobCollectionView.as_view(), name="research-jobs"),
    path("research-jobs/<uuid:job_id>/", ResearchJobDetailView.as_view(), name="research-job-detail"),
    path("health/", HealthView.as_view(), name="recommendations-health"),
]
