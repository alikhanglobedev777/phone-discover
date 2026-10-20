"""User-enabled publication of attributed web facts, explicitly unreviewed."""

import re
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from recommendations.catalog_research import source_url
from .models import Brand, Device, DeviceColor, DeviceImage, DeviceVariant, MarketPriceObservation, ResearchSource
from .research_ingestion import _decimal_price


def _text(value, limit, *, required=False):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid text")
    value = value.strip()
    if required and not value:
        raise ValueError("Missing text")
    return value


def _integer(value, minimum, maximum, *, optional=False):
    if optional and value is None:
        return None
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid numeric specification")
    return value


def _validate(phone, cited):
    if not isinstance(phone, dict):
        raise ValueError("Invalid phone")
    url = source_url(phone.get("source_url"))
    if not url or url not in cited or len(urlsplit(url).path) < 4:
        raise ValueError("A cited product page is required")
    brand = _text(phone.get("brand"), 120, required=True)
    name = _text(phone.get("name"), 180, required=True)
    if name.casefold().startswith(brand.casefold() + " "):
        name = name[len(brand):].strip()
    if not slugify(brand) or not slugify(name):
        raise ValueError("Invalid identity")
    ram = _integer(phone.get("ram_gb"), 1, 64)
    storage = _integer(phone.get("storage_gb"), 1, 4096)
    low = _decimal_price(phone.get("price_min_pkr"))
    high = _decimal_price(phone.get("price_max_pkr"))
    if high < low:
        raise ValueError("Reversed prices")
    condition = phone.get("condition")
    pta = phone.get("pta_status", "unknown")
    listing = phone.get("listing_status", "unknown")
    if condition not in dict(MarketPriceObservation.Condition.choices):
        raise ValueError("Unsupported condition")
    if pta not in dict(MarketPriceObservation.PTAStatus.choices) or listing not in dict(MarketPriceObservation.ListingStatus.choices):
        raise ValueError("Unsupported listing classification")
    specs = phone.get("specifications", {})
    if not isinstance(specs, dict) or len(specs) > 12:
        raise ValueError("Invalid specifications")
    specs = {_text(k, 80, required=True): _text(v, 300, required=True) for k, v in specs.items()}
    image = phone.get("image_url", "")
    if image:
        # No server fetches. Only public source image hosts can enter the UI.
        parts = urlsplit(_text(image, 1000))
        host = (parts.hostname or "").lower()
        if (parts.scheme != "https" or parts.username or parts.password or parts.port
                or not any(host == d or host.endswith("." + d) for d in ("whatmobile.com.pk", "priceoye.pk"))):
            image = ""
    return {
        "brand": brand, "name": name, "url": url, "ram": ram, "storage": storage,
        "minimum": low, "maximum": high, "condition": condition, "pta": pta,
        "city": _text(phone.get("city", ""), 100), "listing": listing,
        "image": image, "specifications": specs,
        "operating_system": _text(phone.get("operating_system", ""), 80),
        "chipset": _text(phone.get("chipset", ""), 160),
        "battery_mah": _integer(phone.get("battery_mah"), 500, 30000, optional=True),
        "display_refresh_hz": _integer(phone.get("display_refresh_hz"), 24, 240, optional=True),
    }


def _validated_options(phone, provider):
    """Optional source-extracted options; never import LLM-written option lists.

    A verified parser in recommendations.source_research adds the private
    marker; the supported search adapters fetch and validate that HTML.
    Human admin updates are separate from this automatic import.
    """
    if provider not in ("tavily", "groq", "source_pages") or phone.get("_source_parsed_options") is not True:
        return [], []
    variants = phone.get("available_variants", [])
    colors = phone.get("available_colors", [])
    if not isinstance(variants, list) or len(variants) > 16 or not isinstance(colors, list) or len(colors) > 16:
        raise ValueError("Too many source options")
    result_variants = []
    for row in variants:
        if not isinstance(row, dict):
            raise ValueError("Invalid source variant")
        pair = (_integer(row.get("ram_gb"), 1, 64), _integer(row.get("storage_gb"), 32, 4096))
        if pair not in result_variants:
            result_variants.append(pair)
    result_colors = []
    for raw in colors:
        name = _text(raw, 60, required=True)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 '\-+()]{1,59}", name):
            raise ValueError("Invalid source finish")
        if name.casefold() not in {value.casefold() for value in result_colors}:
            result_colors.append(name)
    return result_variants, result_colors


def save_catalog_options(device, variants, colors, source_url_value):
    """Add source-confirmed configurations/finishes without inventing prices.

    Existing manually named variants and finish swatches are preserved.
    Provenance URLs are retained in the device's existing JSON field.
    This function must be called inside a database transaction.
    """
    from recommendations.catalog_research import source_url

    url = source_url(source_url_value)
    if not url:
        raise ValueError("Options require an approved source URL")
    created_variants = created_colors = 0
    for ram, storage in variants[:16]:
        if not device.variants.filter(ram_gb=ram, storage_gb=storage).exists():
            _, created = DeviceVariant.objects.get_or_create(
                device=device, name=f"{ram}GB / {storage}GB",
                defaults={"ram_gb": ram, "storage_gb": storage},
            )
            created_variants += int(created)
    for name in colors[:16]:
        if not device.colors.filter(name__iexact=name).exists():
            _, created = DeviceColor.objects.get_or_create(
                device=device, name=name, defaults={"hex_code": ""},
            )
            created_colors += int(created)
    if variants or colors:
        specs = dict(device.specifications) if isinstance(device.specifications, dict) else {}
        provenance = specs.get("_web_option_sources", [])
        provenance = [v for v in provenance if isinstance(v, str)] if isinstance(provenance, list) else []
        if url not in provenance:
            provenance = (provenance + [url])[-12:]
            specs["_web_option_sources"] = provenance
            device.specifications = specs
            device.save(update_fields=["specifications", "updated_at"])
    return created_variants, created_colors


def import_web_phones(research):
    stats = {"devices_created": 0, "prices_saved": 0, "variants_created": 0, "colors_created": 0, "rejected": 0}
    slugs = []
    if research.get("status") != "grounded_preview":
        return stats, slugs
    cited = {source_url(item.get("url")) for item in research.get("sources", []) if isinstance(item, dict)} - {None}
    phones = research.get("document", {}).get("phones", [])
    maximum = 8 if research.get("provider") in ("tavily", "groq", "source_pages") else 4
    if not isinstance(phones, list) or len(phones) > maximum:
        return stats, slugs
    for phone in phones:
        try:
            facts = _validate(phone, cited)
            extra_variants, extra_colors = _validated_options(phone, research.get("provider"))
            with transaction.atomic():
                now = timezone.now()
                source, _ = ResearchSource.objects.get_or_create(url=facts["url"], defaults={
                    "title": f"{facts['brand']} {facts['name']}", "publisher": urlsplit(facts["url"]).hostname,
                    "reuse_status": "permitted", "source_type": "retailer" if "priceoye.pk" in facts["url"] else "other",
                    "reuse_notes": "User-enabled local import of limited attributed product facts from configured sources. No publisher license is asserted; no descriptions, reviews or contact details copied.",
                })
                if source.reuse_status != "permitted" or not source.reuse_notes.strip():
                    raise ValueError("Existing source requires review")
                brand, _ = Brand.objects.get_or_create(slug=slugify(facts["brand"]), defaults={"name": facts["brand"]})
                if not brand.is_active:
                    raise ValueError("Brand is disabled")
                device = Device.objects.filter(brand=brand, name__iexact=facts["name"]).first()
                created = False
                if device is None:
                    device, created = Device.objects.get_or_create(slug=slugify(f"{brand.slug}-{facts['name']}"), defaults={
                        "brand": brand, "name": facts["name"], "is_published": True, "data_source": "web_research",
                        "summary": "Web-researched product facts. See the linked price source; independent review is pending.",
                        "operating_system": facts["operating_system"], "specifications": facts["specifications"],
                        "primary_image_url": facts["image"],
                    })
                if not device.is_published or device.brand_id != brand.pk:
                    raise ValueError("Existing phone is unpublished or has a conflicting identity")
                if facts["image"] and not device.primary_image_url:
                    device.primary_image_url = facts["image"]
                    device.save(update_fields=["primary_image_url", "updated_at"])
                if facts["image"]:
                    DeviceImage.objects.get_or_create(device=device, image_url=facts["image"], defaults={
                        "alt_text": f"{brand.name} {device.name} (source product image)",
                        "is_primary": device.primary_image_url == facts["image"],
                    })
                variant = DeviceVariant.objects.filter(device=device, ram_gb=facts["ram"], storage_gb=facts["storage"]).first()
                primary_created = False
                if variant is None:
                    variant, primary_created = DeviceVariant.objects.get_or_create(device=device, name=f"{facts['ram']}GB / {facts['storage']}GB", defaults={
                        "ram_gb": facts["ram"], "storage_gb": facts["storage"], "chipset": facts["chipset"],
                        "battery_mah": facts["battery_mah"], "display_refresh_hz": facts["display_refresh_hz"]})
                # Serialize imports for the same variant across different searches.
                DeviceVariant.objects.select_for_update().get(pk=variant.pk)
                # Preserve rejected/verified rows and independent review decisions.
                if MarketPriceObservation.objects.filter(
                    variant=variant, source=source, condition=facts["condition"], city=facts["city"],
                    pta_status=facts["pta"], verification_status="rejected",
                ).exists():
                    raise ValueError("This source observation was rejected")
                observation, _ = MarketPriceObservation.objects.get_or_create(
                    variant=variant, source=source, condition=facts["condition"], city=facts["city"],
                    pta_status=facts["pta"], verification_status="web_reported", defaults={
                        "price_min_pkr": facts["minimum"], "price_max_pkr": facts["maximum"],
                    },
                )
                observation.price_min_pkr = facts["minimum"]
                observation.price_max_pkr = facts["maximum"]
                observation.pta_verification = "unknown" if facts["pta"] == "unknown" else "reported"
                observation.listing_url = facts["url"]
                observation.listing_status = facts["listing"]
                observation.observed_at = now
                observation.reviewed_at = None
                observation.notes = "Automatically extracted from source-linked research at this retrieval time. Price, specifications, city and seller-reported PTA status have not been independently reviewed."
                observation.full_clean()
                observation.save()
                source.last_checked_at = now
                source.save(update_fields=["last_checked_at", "updated_at"])
                created_variants, created_colors = save_catalog_options(
                    device, extra_variants, extra_colors, facts["url"]
                )
            stats["variants_created"] += int(primary_created) + created_variants
            stats["colors_created"] += created_colors
            stats["devices_created"] += int(created)
            stats["prices_saved"] += 1
            slugs.append(device.slug)
        except (ValueError, TypeError, KeyError, ValidationError):
            stats["rejected"] += 1
    return stats, list(dict.fromkeys(slugs))
