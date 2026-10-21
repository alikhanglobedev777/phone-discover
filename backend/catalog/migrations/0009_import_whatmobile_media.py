"""One-time, additive WhatMobile photo and color enrichment.

Source: backend/data/whatmobile_media.csv, scanned and exactly identity-matched
on a published WhatMobile product page. The site owner's permission to use
WhatMobile images was confirmed by the Phone Discover operator.

This migration is committed TOGETHER with the validated image manifest.
It does not delete or replace any existing image, phone, variant or price.
"""
import csv
from pathlib import Path
from urllib.parse import urlsplit

from django.db import migrations


def _host_matches(url):
    try:
        info = urlsplit(url)
        return info.scheme == "https" and info.hostname in (
            "whatmobile.com.pk", "www.whatmobile.com.pk"
        )
    except ValueError:
        return False


def import_whatmobile_media(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    DeviceImage = apps.get_model("catalog", "DeviceImage")
    DeviceColor = apps.get_model("catalog", "DeviceColor")
    csv_path = Path(__file__).resolve().parents[2] / "data" / "whatmobile_media.csv"
    if not csv_path.is_file():
        # The manifest is always bundled with this migration. An absent file
        # is a deployment error, not a silent successful import.
        raise RuntimeError(f"WhatMobile media manifest missing: {csv_path}")

    existing = {
        (obj.brand.name.casefold(), obj.name.casefold()): obj
        for obj in Device.objects.select_related("brand").filter(is_published=True)
    }
    already_imaged = set(
        DeviceImage.objects.values_list("device_id", flat=True).distinct()
    )
    images = []
    new_colors = []
    updates = []
    seen = set()
    source_count = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        needed = {"brand", "device", "source", "product_page",
                  "image_url", "colors", "review_status"}
        if not needed.issubset(reader.fieldnames or []):
            raise RuntimeError("WhatMobile image manifest lacks required columns.")
        for line, row in enumerate(reader, start=2):
            brand, name = row["brand"].strip(), row["device"].strip()
            key = (brand.casefold(), name.casefold())
            if key in seen:
                raise RuntimeError(f"Duplicate WhatMobile model identity at line {line}")
            seen.add(key)
            if (row["source"] != "WhatMobile" or
                row["review_status"] != "USER_CONFIRMED_WHATMOBILE" or
                not _host_matches(row["product_page"]) or
                not _host_matches(row["image_url"]) or
                "/admin/images/" not in urlsplit(row["image_url"]).path.lower() or
                len(row["image_url"]) > 1000):
                raise RuntimeError(f"Untrusted WhatMobile media record at line {line}")
            source_count += 1
            obj = existing.get(key)
            if obj is None:
                continue
            if not obj.primary_image_url and obj.pk not in already_imaged:
                images.append(DeviceImage(
                    device_id=obj.pk,
                    image_url=row["image_url"].strip(),
                    alt_text=f"{obj.brand.name} {obj.name} product photo"[:200],
                    is_primary=True,
                ))
                specs = dict(obj.specifications or {})
                specs["photo_attribution"] = {
                    "source": row["product_page"].strip(),
                    "publisher": "WhatMobile",
                    "reuse_basis": "permission confirmed by Phone Discover operator",
                }
                obj.primary_image_url = row["image_url"].strip()
                obj.specifications = specs
                updates.append(obj)

            colors = [name.strip() for name in row["colors"].split(",") if name.strip()]
            if len(colors) > 12 or any(len(color) > 80 for color in colors):
                raise RuntimeError(f"Invalid color list at line {line}")
            previous = set(DeviceColor.objects.filter(device_id=obj.pk).values_list(
                "name", flat=True
            ))
            for color in colors:
                if color not in previous:
                    new_colors.append(DeviceColor(device_id=obj.pk, name=color))
                    previous.add(color)

    # Atomic with Django migration transaction; safe if deployment fails.
    DeviceImage.objects.bulk_create(images, batch_size=200)
    DeviceColor.objects.bulk_create(new_colors, batch_size=200, ignore_conflicts=True)
    Device.objects.bulk_update(updates, ["primary_image_url", "specifications"], batch_size=200)
    print(f"WhatMobile enrichment: {source_count} matched source records, "
          f"{len(images)} new phone images, {len(new_colors)} new documented finishes; "
          "all preexisting media and prices preserved.", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0008_seed_verified_xiaomi_photos")]
    operations = [migrations.RunPython(import_whatmobile_media, migrations.RunPython.noop)]
