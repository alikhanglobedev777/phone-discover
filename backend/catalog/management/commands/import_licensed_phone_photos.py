"""Add exact-model, Creative Commons-licensed photos to existing catalog phones.

From backend:
  python manage.py import_licensed_phone_photos data/commons_phone_photos_0.csv
  python manage.py import_licensed_phone_photos data/commons_phone_photos_0.csv --apply
Never creates models or modifies prices, variants, or existing product photos.
"""
import csv
from pathlib import Path
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import Device, DeviceImage

LICENSES = {"CC0", "CC BY 2.0", "CC BY 3.0", "CC BY 4.0",
            "CC BY-SA 2.0", "CC BY-SA 3.0", "CC BY-SA 4.0",
            "Public domain", "CC-PD-Mark"}
NEEDED = {"brand", "device", "image_url", "image_page",
          "image_license", "image_license_url", "image_credit", "wikidata_id"}


def read_photos(path):
    if not path.is_file():
        raise CommandError(f"Photo CSV not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not NEEDED.issubset(reader.fieldnames or []):
            raise CommandError("Missing photo CSV columns")
        data = []
        seen = set()
        for line, row in enumerate(reader, 2):
            brand, name = row["brand"].strip(), row["device"].strip()
            url, page = row["image_url"].strip(), row["image_page"].strip()
            license_name = row["image_license"].strip()
            credit = row["image_credit"].strip()
            license_url = row["image_license_url"].strip()
            qid = row["wikidata_id"].strip()
            if not (brand and name and license_name in LICENSES
                    and len(url) <= 1000 and len(credit) <= 250
                    and urlsplit(url).scheme == "https"
                    and urlsplit(url).hostname == "upload.wikimedia.org"
                    and urlsplit(page).scheme == "https"
                    and urlsplit(page).hostname == "commons.wikimedia.org"
                    and (not license_url or urlsplit(license_url).scheme == "https")
                    and qid.startswith("Q") and qid[1:].isdigit()):
                raise CommandError(f"Invalid image source/rights on CSV line {line}")
            key = (brand.casefold(), name.casefold())
            if key in seen:
                raise CommandError(f"Duplicate photo identity in CSV line {line}")
            seen.add(key)
            data.append((key, row))
    return data


class Command(BaseCommand):
    help = "Add Commons-licensed exact-model photos; preserve all existing pictures and PKR prices."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=Path)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        photos = read_photos(options["csv_path"])
        existing = {
            (d.brand.name.casefold(), d.name.casefold()): d
            for d in Device.objects.select_related("brand").filter(is_published=True)
        }
        eligible = []
        skipped = 0
        for key, row in photos:
            device = existing.get(key)
            if not device or device.primary_image_url or device.images.exists():
                skipped += 1
                continue
            eligible.append((device, row))
        self.stdout.write(
            f"Validated {len(photos)} licensed photo rows. "
            f"Eligible missing-image phones: {len(eligible)}; skipped: {skipped}."
        )
        if not options["apply"]:
            self.stdout.write("DRY RUN; no changes made.")
            return
        created = 0
        with transaction.atomic():
            for device, row in eligible:
                locked = Device.objects.select_for_update().get(pk=device.pk)
                if locked.primary_image_url or DeviceImage.objects.filter(device=locked).exists():
                    continue
                url = row["image_url"].strip()
                DeviceImage.objects.create(
                    device=locked, image_url=url,
                    alt_text=f'{locked.brand.name} {locked.name} product photo'[:200],
                    is_primary=True,
                )
                specs = dict(locked.specifications or {})
                specs["photo_attribution"] = {
                    "source": row["image_page"].strip(),
                    "license": row["image_license"].strip(),
                    "license_url": row["image_license_url"].strip(),
                    "credit": row["image_credit"].strip(),
                    "wikidata_id": row["wikidata_id"].strip(),
                }
                locked.primary_image_url = url
                locked.specifications = specs
                locked.save(update_fields=["primary_image_url", "specifications", "updated_at"])
                created += 1
        self.stdout.write(self.style.SUCCESS(
            f"Added {created} documented product photos. "
            "Existing phones, colors, variants, prices and photos were preserved."
        ))
