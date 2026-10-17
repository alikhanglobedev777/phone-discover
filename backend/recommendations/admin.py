from django.contrib import admin

from .models import RecommendationQuery, ResearchJob


@admin.register(RecommendationQuery)
class RecommendationQueryAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "country_code",
        "currency",
        "budget",
        "priority_summary",
        "result_count",
        "response_source",
    )
    list_filter = ("country_code", "currency", "response_source", "created_at")
    search_fields = ("query_text", "session_id")
    readonly_fields = (
        "id",
        "session_id",
        "query_text",
        "country_code",
        "currency",
        "budget",
        "priorities",
        "criteria",
        "results",
        "result_count",
        "response_source",
        "created_at",
    )
    date_hierarchy = "created_at"

    @admin.display(description="Priorities")
    def priority_summary(self, obj):
        return ", ".join(obj.priorities) or "Balanced"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ResearchJob)
class ResearchJobAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "requested_by", "created_at", "finished_at")
    list_filter = ("status", "created_at")
    readonly_fields = ("id", "requested_by", "criteria", "status", "counts", "notice", "created_at", "started_at", "finished_at")
    search_fields = ("id",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
