"""Permission-aware, read-only summary counters for the Django admin homepage."""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def phone_discover_admin_stats(context):
    """Show only counts for models the current staff member may view.

    No writes, network calls, refresh launches, or expensive full-table scans
    beyond aggregate counts occur while rendering the dashboard.
    """
    request = context.get("request")
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_staff:
        return {}

    from catalog.models import Device, MarketPriceObservation, PriceRefreshRun, ReviewStatus

    def can_view(model_name):
        return (
            user.is_superuser
            or user.has_perm(f"catalog.view_{model_name}")
            or user.has_perm(f"catalog.change_{model_name}")
        )

    result = {
        "show_devices": can_view("device"),
        "show_prices": can_view("marketpriceobservation"),
        "show_refresh": can_view("pricerefreshrun"),
    }
    if result["show_devices"]:
        result["total_devices"] = Device.objects.count()
        result["published_devices"] = Device.objects.filter(is_published=True).count()
    if result["show_prices"]:
        result["total_prices"] = MarketPriceObservation.objects.count()
        result["unreviewed_prices"] = MarketPriceObservation.objects.filter(
            verification_status__in=(ReviewStatus.PENDING, "web_reported")
        ).count()
    if result["show_refresh"]:
        result["latest_refresh"] = PriceRefreshRun.objects.order_by("-created_at", "-pk").first()
    return result
