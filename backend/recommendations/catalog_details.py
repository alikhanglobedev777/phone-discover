"""Read-only local catalog facts for exact-phone conversations.

No price inference, web requests, or unpublished device exposure.
"""
from catalog.models import Device
from .model_identity import matches_phone_model


def exact_catalog_details(criteria):
    query = criteria.get("device_query")
    if not query:
        return []
    devices = (Device.objects.filter(is_published=True)
               .select_related("brand")
               .prefetch_related("variants", "specification_sections__items"))
    if criteria.get("brand"):
        devices = devices.filter(brand__slug__iexact=criteria["brand"])
    matches = []
    for device in devices:
        if not matches_phone_model(query, device.brand.name, device.name):
            continue
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
        matches.append({
            "slug": device.slug, "brand": device.brand.name, "name": device.name,
            "summary": device.summary, "operating_system": device.operating_system,
            "primary_image_url": device.primary_image_url,
            "specification_sections": sections, "variants": variants,
            "detail_api_url": f"/api/catalog/devices/{device.slug}/",
        })
        if len(matches) >= 3:
            break
    return matches
