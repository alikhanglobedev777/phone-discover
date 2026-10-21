"""Safely enrich existing phones with factual color options; images require rights.

python manage.py import_retailer_phone_metadata data/retailer_image_candidates.csv
python manage.py import_retailer_phone_metadata data/retailer_image_candidates.csv --apply-colors

Publisher photos are proprietary. To hotlink them, operator must first obtain
publisher permission, verify URLs load on the public site, and explicitly pass
--apply-images --confirm-image-rights. No images are downloaded or rehosted.
"""
import csv
from pathlib import Path
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import Device, DeviceColor, DeviceImage

REQUIRED = {"brand", "device", "source", "product_page", "image_url",
            "colors", "review_status"}
HOSTS = {"WhatMobile": "whatmobile.com.pk", "PriceOye": "priceoye.pk"}


def host_matches(url, host):
    parts = urlsplit(url)
    return parts.scheme == "https" and bool(parts.hostname) and (
        parts.hostname == host or parts.hostname.endswith("." + host)
    )


def load_manifest(path):
    if not path.is_file():
        raise CommandError(f"Candidate manifest not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise CommandError("Not a complete retailer image and color report.")
        result = []
        seen = set()
        for line, row in enumerate(reader, 2):
            brand = row["brand"].strip()
            name = row["device"].strip()
            site = row["source"].strip()
            if site not in HOSTS or not brand or not name:
                raise CommandError(f"Unrecognized phone or site, line {line}")
            if (brand.casefold(), name.casefold()) in seen:
                raise CommandError(f"Duplicate identity on line {line}")
            seen.add((brand.casefold(), name.casefold()))
            if (not host_matches(row["product_page"], HOSTS[site])
                    or not host_matches(row["image_url"], HOSTS[site])
                    or row["review_status"].strip() not in ("REQUIRES_REUSE_RIGHTS", "RIGHTS_VERIFIED")):
                raise CommandError(f"Invalid source or rights flag on line {line}")
            if len(row["image_url"]) > 1000:
                raise CommandError(f"Image URL too long, line {line}")
            color_list = [color.strip() for color in row["colors"].split(",")
                          if color.strip()]
            if len(color_list) > 12 or any(len(c) > 80 for c in color_list):
                raise CommandError(f"Invalid colors on line {line}")
            result.append((brand, name, site, row, color_list))
    return result


class Command(BaseCommand):
    help = "Import documented phone finishes; proprietary retailer images need rights approval."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=Path)
        parser.add_argument("--apply-colors", action="store_true")
        parser.add_argument("--apply-images", action="store_true")
        parser.add_argument("--confirm-image-rights", action="store_true")

    def handle(self, *args, **opts):
        manifest = load_manifest(opts["csv_path"])
        if opts["apply_images"] and not opts["confirm_image_rights"]:
            raise CommandError("Obtain site owner's image-reuse authorization before --confirm-image-rights.")
        # Approval must be attached to each source row, not inferred from the flag alone.
        if opts["apply_images"] and any(row["review_status"] != "RIGHTS_VERIFIED"
                                        for _, _, _, row, _ in manifest):
            raise CommandError("Images are still marked REQUIRES_REUSE_RIGHTS; "
                               "verify each source's reuse permission before changing its status.")
        existing = {
            (d.brand.name.casefold(), d.name.casefold()): d
            for d in Device.objects.select_related("brand").filter(is_published=True)
        }
        eligible = [(existing[(brand.casefold(), name.casefold())], site, row, colors)
                    for brand, name, site, row, colors in manifest
                    if (brand.casefold(), name.casefold()) in existing]
        self.stdout.write(f"Research entries {len(manifest)}; exact matches to existing phones: {len(eligible)}")
        if not opts["apply_colors"] and not opts["apply_images"]:
            self.stdout.write("DRY RUN — no database changes.")
            return
        created_colors = 0
        created_images = 0
        with transaction.atomic():
            for device, site, row, colors in eligible:
                if opts["apply_colors"]:
                    for color in colors:
                        _, was_created = DeviceColor.objects.get_or_create(
                            device=device, name=color)
                        created_colors += int(was_created)
                if opts["apply_images"]:
                    locked = Device.objects.select_for_update().get(pk=device.pk)
                    if locked.primary_image_url or locked.images.exists():
                        continue
                    url = row["image_url"].strip()
                    DeviceImage.objects.create(
                        device=locked, image_url=url,
                        alt_text=f"{locked.brand.name} {locked.name} product photo"[:200],
                        is_primary=True,
                    )
                    specs = dict(locked.specifications or {})
                    specs["photo_attribution"] = {
                        "source": row["product_page"], "publisher": site,
                        "rights_verification": "publisher permission independently verified",
                    }
                    locked.specifications = specs
                    locked.primary_image_url = url
                    locked.save(update_fields=["primary_image_url", "specifications", "updated_at"])
                    created_images += 1
        self.stdout.write(self.style.SUCCESS(
            f"Added {created_colors} documented finishes and {created_images} approved image links. "
            "No existing prices, RAM/storage variants, or phone identities changed."
        ))
