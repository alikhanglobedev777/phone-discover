import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from catalog.models import Brand, Device, DeviceVariant, MarketOffer


class Command(BaseCommand):
    help = "Import a catalog CSV with one device variant and optional market offer per row."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        if not csv_path.exists():
            raise CommandError(f"CSV file does not exist: {csv_path}")
        required = {"brand", "device", "variant", "ram_gb", "storage_gb"}
        imported = 0
        with csv_path.open(newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise CommandError(f"Missing required columns: {', '.join(sorted(missing))}")
            for row in reader:
                brand, _ = Brand.objects.get_or_create(name=row["brand"].strip(), defaults={"slug": slugify(row["brand"])})
                device, _ = Device.objects.update_or_create(
                    slug=slugify(f"{brand.name}-{row['device']}"),
                    defaults={
                        "brand": brand,
                        "name": row["device"].strip(),
                        "summary": row.get("summary", "").strip(),
                        "operating_system": row.get("operating_system", "").strip(),
                        "status": row.get("status", Device.Status.AVAILABLE).strip().lower(),
                        "primary_image_url": row.get("primary_image_url", "").strip(),
                        "official_url": row.get("official_url", "").strip(),
                        "is_published": row.get("is_published", "true").lower() == "true",
                    },
                )
                variant, _ = DeviceVariant.objects.update_or_create(
                    device=device,
                    name=row["variant"].strip(),
                    defaults={
                        "ram_gb": int(row["ram_gb"]),
                        "storage_gb": int(row["storage_gb"]),
                        "battery_mah": int(row["battery_mah"]) if row.get("battery_mah") else None,
                        "display_refresh_hz": int(row["display_refresh_hz"]) if row.get("display_refresh_hz") else None,
                        "chipset": row.get("chipset", "").strip(),
                        "camera_score": row.get("camera_score") or 0,
                        "gaming_score": row.get("gaming_score") or 0,
                        "battery_score": row.get("battery_score") or 0,
                    },
                )
                if row.get("country_code") and row.get("price") and row.get("product_url"):
                    MarketOffer.objects.update_or_create(
                        variant=variant,
                        country_code=row["country_code"].upper(),
                        seller_name=row.get("seller_name", "Imported seller"),
                        defaults={
                            "currency": row.get("currency", "USD").upper(),
                            "price": row["price"],
                            "product_url": row["product_url"],
                            "is_affiliate": row.get("is_affiliate", "false").lower() == "true",
                        },
                    )
                imported += 1
        self.stdout.write(self.style.SUCCESS(f"Imported {imported} catalog rows."))
