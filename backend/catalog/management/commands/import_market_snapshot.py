"""Import a locally reviewed factual snapshot, never scrape or generate prices."""

import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from catalog.models import (
    Brand, Device, DeviceImage, DeviceVariant, MarketPriceObservation, ResearchSource,
    ReviewStatus, SpecificationItem, SpecificationSection,
)


class Command(BaseCommand):
    help = "Import a reviewed local JSON snapshot with source-linked Pakistani prices."

    def add_arguments(self, parser):
        parser.add_argument("snapshot", type=Path)

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            data = json.loads(options["snapshot"].read_text(encoding="utf-8"))
            observed = parse_datetime(data["observed_at"])
            if not observed or timezone.is_naive(observed) or observed > timezone.now():
                raise ValueError("observed_at must be a past, timezone-aware timestamp")
            review = data["review_notes"].strip()
            reuse = data["reuse_notes"].strip()
            if not review or not reuse:
                raise ValueError("Document the evidence review and intended source use")
            created_devices = created_prices = 0
            for item in data["devices"]:
                brand, _ = Brand.objects.get_or_create(
                    slug=slugify(item["brand"]), defaults={"name": item["brand"]},
                )
                # Re-imports must not republish or overwrite later admin edits.
                device, created = Device.objects.get_or_create(
                    slug=item["slug"], defaults={
                        "brand": brand, "name": item["name"], "is_published": True,
                        "operating_system": item["operating_system"],
                        "summary": "Source-reported specifications; Pakistani asking prices are linked separately.",
                        "specifications": item["specifications"],
                    },
                )
                created_devices += created
                if device.brand_id != brand.pk or device.name != item["name"]:
                    raise ValueError("Existing device identity conflicts with snapshot")
                image_url = item.get("primary_image_url", "").strip()
                if image_url:
                    URLValidator(schemes=["https"])(image_url)
                    # Fill missing artwork, preserving an image selected in admin.
                    if not device.primary_image_url:
                        device.primary_image_url = image_url
                        device.save(update_fields=["primary_image_url", "updated_at"])
                    DeviceImage.objects.get_or_create(
                        device=device, image_url=image_url, defaults={
                            "alt_text": f"{item['brand']} {item['name']} product image",
                            "is_primary": device.primary_image_url == image_url,
                            "sort_order": 0,
                        },
                    )
                variant, _ = DeviceVariant.objects.get_or_create(
                    device=device, name=f"{item['ram_gb']}GB / {item['storage_gb']}GB",
                    defaults={key: item[key] for key in (
                        "ram_gb", "storage_gb", "chipset", "battery_mah", "display_refresh_hz",
                    )},
                )
                if (variant.ram_gb, variant.storage_gb) != (item["ram_gb"], item["storage_gb"]):
                    raise ValueError("Existing variant conflicts with snapshot")
                if created:
                    section = SpecificationSection.objects.create(
                        device=device, slug="source-reported", name="Source-reported specifications",
                    )
                    for order, (label, value) in enumerate(item["specifications"].items()):
                        SpecificationItem.objects.create(section=section, label=label, value=value, sort_order=order)
                for price in item["prices"]:
                    source, _ = ResearchSource.objects.get_or_create(
                        url=price["url"], defaults={
                            "title": f"{item['brand']} {item['name']} - {price['publisher']}",
                            "publisher": price["publisher"],
                            "source_type": "retailer" if price["publisher"] == "PriceOye" else "other",
                            "reuse_status": ResearchSource.ReuseStatus.PERMITTED,
                            "reuse_notes": reuse, "last_checked_at": observed,
                        },
                    )
                    source.full_clean()
                    if source.reuse_status != ResearchSource.ReuseStatus.PERMITTED or not source.reuse_notes.strip():
                        raise ValueError("Existing source has not been cleared for intended use")
                    observation, new = MarketPriceObservation.objects.get_or_create(
                        variant=variant, source=source, observed_at=observed,
                        defaults={
                            "condition": "box_pack", "pta_status": "unknown", "pta_verification": "unknown",
                            "city": "", "listing_url": source.url,
                            "seller_name": price["publisher"] if source.source_type == "retailer" else "",
                            "listing_status": price["listing_status"],
                            "price_min_pkr": price["price_pkr"], "price_max_pkr": price["price_pkr"],
                            "verification_status": ReviewStatus.VERIFIED, "reviewed_at": observed,
                            "notes": review + " " + price.get("note", ""),
                        },
                    )
                    observation.full_clean()
                    created_prices += new
        except (OSError, ValueError, TypeError, KeyError, ValidationError) as exc:
            raise CommandError(f"Snapshot import rolled back: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(
            f"Created {created_devices} phones and {created_prices} price observations. "
            "Original observation dates preserved; PTA and availability remain unconfirmed."
        ))
