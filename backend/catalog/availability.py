"""Public catalog readiness without exposing unpublished records."""

from django.db.models import Q
from django.db.models.functions import Trim

from .models import Device
from .pricing import eligible_price_observations


def catalog_availability(*, as_of=None):
    if not Device.objects.filter(is_published=True).exists():
        return "empty"
    prices = eligible_price_observations(as_of=as_of).filter(variant__device__is_published=True)
    prices = prices.annotate(evidence_notes=Trim("notes"), rights_notes=Trim("source__reuse_notes"))
    if not prices.filter(
        (Q(source__isnull=True) & ~Q(evidence_notes=""))
        | (Q(source__isnull=False) & ~Q(rights_notes=""))
    ).exists():
        return "missing_prices"
    return "ready"
