"""Reviewable CSV sync for source-backed smartphone specifications, never PKR prices."""
import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from catalog.models import Brand, Device, DeviceColor, DeviceVariant

ALLOWED = {"apple", "samsung", "google", "oppo", "vivo", "xiaomi",
           "motorola", "infinix", "tecno", "itel"}
REQUIRED = {"brand", "device", "release_date", "ram_gb", "storage_gb", "source_urls"}

class Command(BaseCommand):
    help = "Dry-run or upsert source-backed 2020+ phone CSV. Never deletes prices or unlisted phones."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=Path)
        parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
        parser.add_argument("--minimum-models", type=int, default=100,
                            help="Abort under this many distinct models (default 100)")

    def handle(self, *args, **options):
        file = options["csv_path"]
        if not file.is_file():
            raise CommandError(f"CSV not found: {file}")
        grouped = defaultdict(list)
        with file.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if not REQUIRED.issubset(reader.fieldnames or []):
                raise CommandError("Missing CSV fields: " + ", ".join(sorted(REQUIRED - set(reader.fieldnames or []))))
            for number, row in enumerate(reader, 2):
                try:
                    brand = row["brand"].strip()
                    name = row["device"].strip()
                    released = date.fromisoformat(row["release_date"])
                    ram, storage = int(row["ram_gb"]), int(row["storage_gb"])
                    urls = json.loads(row["source_urls"])
                    colors = json.loads(row.get("colors") or "[]")
                    if (brand.casefold() not in ALLOWED or not name or len(name) > 180
                        or not 2020 <= released.year <= date.today().year
                        or released > date.today()
                        or not 1 <= ram <= 64 or not 4 <= storage <= 4096
                        or not isinstance(urls, list) or not urls
                        or not all(isinstance(u, str) and u.startswith("https://") for u in urls)
                        or not isinstance(colors, list) or len(colors) > 16
                        or not all(isinstance(c, str) and 1 < len(c.strip()) <= 80 for c in colors)):
                        raise ValueError("Invalid model, source, memory or colors")
                    grouped[(brand, name)].append((row, released, ram, storage, colors))
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    raise CommandError(f"Invalid row {number}: {exc}") from exc
        if len(grouped) < options["minimum_models"]:
            raise CommandError(f"Only {len(grouped)} models, minimum {options['minimum_models']}; no writes")
        counts = defaultdict(int)
        for (brand_name, name), rows in sorted(grouped.items()):
            if len({x[1] for x in rows}) > 1:
                raise CommandError(f"Conflicting release dates for {brand_name} {name}")
            counts["models"] += 1
            counts["variants"] += len(set((x[2], x[3]) for x in rows))
        self.stdout.write(f"Validated {counts['models']} models / {counts['variants']} variant pairs.")
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("DRY RUN. No changes written. Pass --apply after backing up PostgreSQL."))
            return
        with transaction.atomic():
            for (brand_name, name), rows in sorted(grouped.items()):
                brand, _ = Brand.objects.get_or_create(
                    slug=slugify(brand_name), defaults={"name": brand_name, "is_active": True})
                slug = slugify(f"{brand_name}-{name}")
                defaults = {"brand": brand, "name": name, "release_date": rows[0][1],
                            "data_source": "catalog"}
                device, created = Device.objects.get_or_create(slug=slug, defaults=defaults)
                if device.brand_id != brand.id:
                    raise CommandError(f"Brand conflict: {slug}")
                if not created:
                    # Preserve admin-managed summary, images, status, visibility, existing PKR prices.
                    device.name = name
                    device.release_date = rows[0][1]
                    device.save(update_fields=["name", "release_date", "updated_at"])
                for row, _, ram, storage, colors in rows:
                    variant_name = f"{ram}GB RAM / {storage}GB Storage"
                    variant = DeviceVariant.objects.filter(device=device, ram_gb=ram, storage_gb=storage).first()
                    if not variant:
                        variant = DeviceVariant(device=device, name=variant_name,
                                                ram_gb=ram, storage_gb=storage)
                    if not variant.pk or not variant.chipset:
                        variant.chipset = row.get("chipset", "")[:160]
                    if not variant.pk and row.get("battery_mah"):
                        variant.battery_mah = int(row["battery_mah"])
                    if not variant.pk and row.get("display_refresh_hz"):
                        variant.display_refresh_hz = int(row["display_refresh_hz"])
                    variant.full_clean()
                    variant.save()
                    for color in colors:
                        DeviceColor.objects.get_or_create(device=device, name=color.strip())
            self.stdout.write(self.style.SUCCESS(
                f"Upserted {counts['models']} models; existing PKR prices and other models were preserved."))
