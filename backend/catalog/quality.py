"""Production-safe source coverage metrics: read-only and cached."""
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from .models import Device, DeviceClaim, DeviceVariant, ReviewStatus, ResearchSource

CACHE_KEY = "catalog_data_quality_v1"


def catalog_quality_snapshot():
    result = cache.get(CACHE_KEY)
    if result is not None:
        return result
    from django.db.models import Count
    threshold = timezone.now() - timedelta(days=365)
    published = Device.objects.filter(is_published=True)
    variants = DeviceVariant.objects.filter(device__is_published=True)
    result = {
        "published_devices": published.count(),
        "published_variants": variants.count(),
        "devices_recently_verified": published.filter(last_verified_at__gte=threshold).count(),
        "devices_with_official_link": published.exclude(official_url="").count(),
        "variants_with_camera_editorial_score": variants.filter(camera_score__gt=0).count(),
        "variants_with_gaming_editorial_score": variants.filter(gaming_score__gt=0).count(),
        "variants_with_battery_editorial_score": variants.filter(battery_score__gt=0).count(),
        "reviewed_source_claims": DeviceClaim.objects.filter(
            status=ReviewStatus.VERIFIED, reviewed_at__isnull=False,
            device__is_published=True,
            source__reuse_status=ResearchSource.ReuseStatus.PERMITTED,
        ).count(),
        "caution": (
            "Coverage counts do not validate every fact. Unattributed editorial "
            "scores are not independent benchmarks; no score is invented."
        ),
    }
    cache.set(CACHE_KEY, result, 900)
    return result
