"""Add individually licensed Wikimedia images for phones still without photos.

This is a second source, separate from operator-authorized WhatMobile.
Only exact manufacturer/model matching from Wikimedia P18; CC/PD license
information is preserved. Existing media, prices, variants, and colors untouched.
"""
import csv
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from django.db import migrations

LICENSES = {"CC0", "CC BY 2.0", "CC BY 3.0", "CC BY 4.0",
            "CC BY-SA 2.0", "CC BY-SA 3.0", "CC BY-SA 4.0",
            "Public domain", "CC-PD-Mark"}
FIELDS = {"brand", "device", "image_url", "image_page",
          "image_license", "image_license_url", "image_credit", "wikidata_id"}


def host(url, expected):
    try:
        return urlsplit(url).scheme == "https" and urlsplit(url).hostname == expected
    except ValueError:
        return False


def import_cc_images(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Image = apps.get_model("catalog", "DeviceImage")
    path = Path(__file__).resolve().parents[2] / "data" / "commons_phone_photos.csv"
    if not path.is_file():
        raise RuntimeError("Wikimedia photo evidence not bundled with migration")
    records = []
    seen = set()
    image_models = defaultdict(set)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not FIELDS.issubset(reader.fieldnames or []):
            raise RuntimeError("Incorrect licensed image manifest columns")
        for number, row in enumerate(reader, 2):
            key = (row["brand"].strip().casefold(), row["device"].strip().casefold())
            if (not all(key) or key in seen or
                row["image_license"] not in LICENSES or
                not host(row["image_url"], "upload.wikimedia.org") or
                not host(row["image_page"], "commons.wikimedia.org") or
                (row["image_license_url"] and
                 urlsplit(row["image_license_url"]).scheme != "https") or
                len(row["image_url"]) > 1000 or len(row["image_credit"]) > 250 or
                not row["wikidata_id"].startswith("Q") or
                not row["wikidata_id"][1:].isdigit()):
                raise RuntimeError(f"Invalid source rights/model identity line {number}")
            seen.add(key)
            image_models[row["image_url"]].add(key)
            records.append((key, row))
    if not records:
        raise RuntimeError("No licensed model photos to import")
    conflicting_images = {url for url, owners in image_models.items() if len(owners) > 1}
    existing = {
        (d.brand.name.casefold(), d.name.casefold()): d
        for d in Device.objects.select_related("brand").filter(is_published=True)
    }
    occupied = set(Image.objects.values_list("device_id", flat=True))
    pictures = []
    updates = []
    for key, row in records:
        device = existing.get(key)
        if (device is None or device.pk in occupied or device.primary_image_url or
                row["image_url"] in conflicting_images):
            continue
        pictures.append(Image(
            device_id=device.pk, image_url=row["image_url"],
            is_primary=True, alt_text=f"{device.brand.name} {device.name} photograph"[:200],
        ))
        specs = dict(device.specifications or {})
        specs["photo_attribution"] = {
            "source": row["image_page"], "license": row["image_license"],
            "license_url": row["image_license_url"],
            "credit": row["image_credit"], "wikidata_id": row["wikidata_id"],
        }
        device.specifications = specs
        device.primary_image_url = row["image_url"]
        occupied.add(device.pk)
        updates.append(device)
    Image.objects.bulk_create(pictures, ignore_conflicts=True, batch_size=150)
    Device.objects.bulk_update(updates, ["specifications", "primary_image_url"], batch_size=150)
    print(f"Added {len(pictures)} separately licensed missing-phone photos "
          f"from {len(records)} source-backed exact-model records.", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0011_import_whatmobile_details")]
    operations = [migrations.RunPython(import_cc_images, migrations.RunPython.noop)]
