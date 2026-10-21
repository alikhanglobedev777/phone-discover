"""Fast create-only import of curated TechAPI CSV. Existing catalog and prices untouched.

Run from backend:
  python manage.py import_curated_phone_catalog data/phones_import_ready.csv
  python manage.py import_curated_phone_catalog data/phones_import_ready.csv --apply --publish-new
"""
import csv
import hashlib
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils.text import slugify

from catalog.models import Brand, Device, DeviceColor, DeviceVariant
from scripts.prepare_production_catalog import stable_slug

ALLOWED = {"apple", "samsung", "google", "oppo", "vivo", "xiaomi",
           "motorola", "infinix", "tecno", "itel"}


def load_catalog(path):
    if not path.is_file():
        raise CommandError(f"CSV not found: {path}")
    grouped = defaultdict(list)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        needed = {"brand", "device", "release_date", "ram_gb",
                  "storage_gb", "source_urls", "colors"}
        if not needed.issubset(reader.fieldnames or []):
            raise CommandError("Missing columns: " +
                               ", ".join(sorted(needed - set(reader.fieldnames or []))))
        for number, row in enumerate(reader, 2):
            try:
                brand, name = row["brand"].strip(), row["device"].strip()
                if brand.casefold() not in ALLOWED or not 2 <= len(name) <= 65:
                    raise ValueError("unsupported brand or invalid model name")
                ram, storage = int(row["ram_gb"]), int(row["storage_gb"])
                if not 1 <= ram <= 64 or not 16 <= storage <= 4096:
                    raise ValueError("invalid RAM/storage configuration")
                released = date.fromisoformat(row["release_date"]) if row["release_date"] else None
                if released and (not 2020 <= released.year <= date.today().year
                                 or released > date.today()):
                    raise ValueError("invalid release date")
                urls = json.loads(row["source_urls"])
                colors = json.loads(row.get("colors") or "[]")
                if not isinstance(urls, list) or not urls or not all(
                    isinstance(url, str) and url.startswith("https://") and len(url) <= 1000
                    for url in urls
                ):
                    raise ValueError("missing or invalid source URLs")
                if not isinstance(colors, list) or len(colors) > 16 or not all(
                    isinstance(c, str) and 1 < len(c.strip()) <= 80 for c in colors
                ):
                    raise ValueError("invalid color names")
                chipset, os_name = (row.get("chipset") or "").strip(), (row.get("operating_system") or "").strip()
                if len(chipset) > 160 or len(os_name) > 80:
                    raise ValueError("specification exceeds field length")
                battery = int(row["battery_mah"]) if row.get("battery_mah") else None
                refresh = int(row["display_refresh_hz"]) if row.get("display_refresh_hz") else None
                if battery is not None and not 500 <= battery <= 30000:
                    raise ValueError("invalid battery")
                if refresh is not None and not 24 <= refresh <= 240:
                    raise ValueError("invalid refresh rate")
                grouped[(brand.casefold(), name.casefold())].append({
                    "brand": brand, "name": name, "date": released,
                    "ram": ram, "storage": storage, "links": urls, "colors": colors,
                    "chipset": chipset, "os": os_name, "battery": battery, "refresh": refresh,
                })
            except (ValueError, TypeError, KeyError) as error:
                raise CommandError(f"Invalid import CSV line {number}: {error}") from error
    if len(grouped) < 500 or {key[0] for key in grouped} != ALLOWED:
        raise CommandError("Insufficient catalog coverage; need >=500 models and all 10 brands")
    slugs = {}
    for key, variants in grouped.items():
        model_slug = stable_slug(variants[0]["brand"], variants[0]["name"])
        if not model_slug or (model_slug in slugs and slugs[model_slug] != key):
            raise CommandError(f"Ambiguous catalog model slug: {model_slug}")
        slugs[model_slug] = key
        dates = {v["date"] for v in variants if v["date"]}
        if len(dates) > 1 or (dates and any(v["date"] is None for v in variants)):
            raise CommandError(f"Conflicting dates remain: {key}")
        memory = [(v["ram"], v["storage"]) for v in variants]
        if len(memory) != len(set(memory)):
            raise CommandError(f"Duplicate RAM/storage variant: {key}")
    return grouped, slugs


class Command(BaseCommand):
    help = "Create-only bulk import of clean models; never alters existing phones, prices, or variants."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=Path)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--publish-new", action="store_true")

    def handle(self, *args, **options):
        path = options["csv_path"]
        grouped, slugs = load_catalog(path)
        num_variants = sum(len(v) for v in grouped.values())
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        self.stdout.write(f"Validated {len(grouped)} phone models / {num_variants} variants; SHA256={sha}")
        if not options["apply"]:
            self.stdout.write("DRY RUN: no database changes.")
            return
        if not options["publish_new"]:
            raise CommandError("Use --publish-new to explicitly approve publishing new catalog entries")
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(64260721)")
            brands = {}
            for name in sorted(ALLOWED):
                brand, _ = Brand.objects.get_or_create(
                    slug=slugify(name), defaults={"name": name.title(), "is_active": True})
                brands[name] = brand
            existing_slugs = set(Device.objects.filter(slug__in=slugs).values_list("slug", flat=True))
            # Prevent duplicates when an admin originally chose a different slug.
            existing_names = {
                (d.brand.slug.casefold(), d.name.casefold())
                for d in Device.objects.select_related("brand").all().iterator()
            }
            new_keys = [
                key for slug, key in slugs.items()
                if slug not in existing_slugs and key not in existing_names
            ]
            pending_devices = []
            for key in new_keys:
                variants = grouped[key]
                first = variants[0]
                all_urls = sorted({url for v in variants for url in v["links"]})
                os_values = {v["os"] for v in variants if v["os"]}
                release = next((v["date"] for v in variants if v["date"]), None)
                pending_devices.append(Device(
                    brand=brands[key[0]], name=first["name"],
                    slug=stable_slug(first["brand"], first["name"]),
                    release_date=release,
                    operating_system=next(iter(os_values)) if len(os_values) == 1 else "",
                    specifications={"catalog_attribution": {
                        "dataset": "GetTechAPI/TechAPI", "license": "CC BY-SA 4.0",
                        "source_urls": all_urls}},
                    data_source="catalog", is_published=True,
                ))
            Device.objects.bulk_create(pending_devices, batch_size=200)
            new_devices = {
                obj.slug: obj for obj in Device.objects.filter(
                    slug__in=[d.slug for d in pending_devices])
            }
            new_variants, new_colors = [], []
            for key in new_keys:
                first = grouped[key][0]
                device = new_devices[stable_slug(first["brand"], first["name"])]
                documented_colors = set()
                for variant in grouped[key]:
                    new_variants.append(DeviceVariant(
                        device=device,
                        name=f'{variant["ram"]}GB RAM / {variant["storage"]}GB Storage',
                        ram_gb=variant["ram"], storage_gb=variant["storage"],
                        chipset=variant["chipset"],
                        battery_mah=variant["battery"],
                        display_refresh_hz=variant["refresh"],
                    ))
                    documented_colors.update(variant["colors"])
                for color in sorted(documented_colors):
                    new_colors.append(DeviceColor(device=device, name=color.strip()))
            DeviceVariant.objects.bulk_create(new_variants, batch_size=200)
            DeviceColor.objects.bulk_create(new_colors, batch_size=200,
                                            ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(
            f"Created and published {len(pending_devices)} phone models / "
            f"{len(new_variants)} variants / {len(new_colors)} colors; "
            f"skipped {len(grouped) - len(new_keys)} existing phones. "
            "No existing phone, price or variant records changed."
        ))
