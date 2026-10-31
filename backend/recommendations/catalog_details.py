"""Read-only, published local catalog facts for exact-model conversations."""
from catalog.models import Device
from .model_identity import matches_phone_model
from .evidence_quality import public_evidence, evidence_prefetch


def _serialize(device):
    sections = [
        {"name": section.name, "items": [
            {"label": item.label, "value": item.value}
            for item in section.items.all() if item.value
        ]}
        for section in device.specification_sections.all()
    ]
    variants = [
        {"ram_gb": variant.ram_gb, "storage_gb": variant.storage_gb,
         "chipset": variant.chipset, "battery_mah": variant.battery_mah,
         "display_refresh_hz": variant.display_refresh_hz}
        for variant in device.variants.all()
    ][:8]
    return {
        "slug": device.slug, "brand": device.brand.name, "name": device.name,
        "summary": device.summary, "operating_system": device.operating_system,
        "primary_image_url": device.primary_image_url,
        "specification_sections": sections, "variants": variants,
        "last_verified_at": device.last_verified_at.isoformat() if device.last_verified_at else None,
        "detail_api_url": f"/api/catalog/devices/{device.slug}/",
        "evidence": public_evidence(device),
    }


def catalog_details_for_slugs(slugs):
    """Only requested published slugs, in caller-supplied order."""
    wanted = list(dict.fromkeys(slugs))[:5]
    if not wanted:
        return []
    devices = (Device.objects.filter(is_published=True, slug__in=wanted)
               .select_related("brand")
               .prefetch_related("variants", "specification_sections__items", evidence_prefetch()))
    by_slug = {device.slug: device for device in devices}
    return [_serialize(by_slug[slug]) for slug in wanted if slug in by_slug]


def exact_catalog_details(criteria):
    query = criteria.get("device_query")
    if not query:
        return []
    devices = Device.objects.filter(is_published=True).select_related("brand")
    if criteria.get("brand"):
        devices = devices.filter(brand__slug__iexact=criteria["brand"])
    # Avoid prefetching rich specifications across the entire phone database.
    ids = [
        device.slug for device in devices.iterator(chunk_size=500)
        if matches_phone_model(query, device.brand.name, device.name)
    ][:3]
    return catalog_details_for_slugs(ids)
