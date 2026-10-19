"""One-click, CSRF-protected refresh dashboard in Django admin."""

from django.contrib import admin, messages
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.urls import path, reverse
from datetime import timedelta
from django.utils import timezone
from recommendations.provider_config import research_available

from .models import PriceRefreshRun
from .price_refresh import launch_async


@admin.register(PriceRefreshRun)
class PriceRefreshRunAdmin(admin.ModelAdmin):
    change_list_template = "admin/catalog/pricerefreshrun/change_list.html"
    list_display = ("id", "origin", "status", "created_at", "started_at", "finished_at", "counts_summary", "notice")
    list_filter = ("status", "origin", "created_at")
    readonly_fields = (
        "status", "origin", "requested_by", "force", "counts", "notice",
        "created_at", "started_at", "finished_at",
    )
    ordering = ("-created_at",)
    list_per_page = 30

    def has_add_permission(self, request):
        return False  # only the guarded admin button / scheduler creates a job

    def has_change_permission(self, request, obj=None):
        return False  # run histories are immutable to admin users

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        return [
            path("refresh-now/", self.admin_site.admin_view(self.refresh_now),
                 name="catalog_pricerefreshrun_refresh_now"),
        ] + super().get_urls()

    @admin.display(description="Results")
    def counts_summary(self, obj):
        counts = obj.counts or {}
        return (f"Checked {counts.get('variants_checked', 0)} · "
                f"Added {counts.get('observations_added', 0)} · "
                f"Blocked {counts.get('blocked_sources', 0)}")

    def refresh_now(self, request):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not request.user.is_superuser:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("Only superusers can start external price research")
        from django.conf import settings
        url = reverse("admin:catalog_pricerefreshrun_changelist")
        if not settings.PRICE_REFRESH_ENABLED or not research_available():
            self.message_user(request, "Price refresh or web research is disabled in backend settings.", messages.ERROR)
            return redirect(url)
        # Process crashes must not permanently disable the admin button.
        now = timezone.now()
        PriceRefreshRun.objects.filter(status="queued", created_at__lt=now - timedelta(minutes=15)).update(
            status="failed", notice="Worker did not start. Retry or check server logs.", finished_at=now)
        PriceRefreshRun.objects.filter(status="running", started_at__lt=now - timedelta(hours=8)).update(
            status="failed", notice="Worker stopped responding. Check logs before retrying.", finished_at=now)
        if PriceRefreshRun.objects.filter(status__in=("queued", "running")).exists():
            self.message_user(request, "A price refresh is already queued/running; check its status below.", messages.WARNING)
            return redirect(url)
        run = PriceRefreshRun.objects.create(origin="admin", force=True, requested_by=request.user)
        if launch_async(run):
            self.message_user(request, f"Price refresh #{run.pk} started in background. Check this page for results.", messages.SUCCESS)
        else:
            self.message_user(request, "Failed to start price refresh. Run the management command manually.", messages.ERROR)
        return redirect(url)
