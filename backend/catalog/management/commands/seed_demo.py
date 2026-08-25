from datetime import date

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from catalog.models import (
    Brand,
    Device,
    DeviceImage,
    DeviceVariant,
    MarketOffer,
    SpecificationItem,
    SpecificationSection,
)


DEMO_DEVICES = [
    {
        "brand": "Nova",
        "name": "Nova One Pro",
        "slug": "nova-one-pro",
        "summary": "A balanced flagship with a strong camera system and fast display.",
        "os": "Android 15",
        "ram": 12,
        "storage": 256,
        "battery": 5000,
        "refresh": 120,
        "chipset": "Nova X1",
        "camera": 92,
        "gaming": 88,
        "battery_score": 90,
        "price": 699,
        "image": "https://placehold.co/600x800?text=Nova+One+Pro",
        "display": "6.7-inch AMOLED, 120 Hz",
        "camera_text": "50 MP wide + 48 MP ultrawide + 12 MP telephoto",
        "charging": "80W wired, 30W wireless",
    },
    {
        "brand": "Atlas",
        "name": "Atlas Play 5G",
        "slug": "atlas-play-5g",
        "summary": "A performance-focused phone for gaming and long battery life.",
        "os": "Android 15",
        "ram": 12,
        "storage": 256,
        "battery": 6000,
        "refresh": 144,
        "chipset": "Atlas G900",
        "camera": 78,
        "gaming": 96,
        "battery_score": 97,
        "price": 449,
        "image": "https://placehold.co/600x800?text=Atlas+Play+5G",
        "display": "6.78-inch AMOLED, 144 Hz",
        "camera_text": "64 MP wide + 8 MP ultrawide",
        "charging": "65W wired",
    },
    {
        "brand": "Pixelia",
        "name": "Pixelia Air",
        "slug": "pixelia-air",
        "summary": "A compact value phone with excellent computational photography.",
        "os": "Android 15",
        "ram": 8,
        "storage": 128,
        "battery": 4700,
        "refresh": 120,
        "chipset": "Pixelia Tensor A",
        "camera": 94,
        "gaming": 74,
        "battery_score": 84,
        "price": 399,
        "image": "https://placehold.co/600x800?text=Pixelia+Air",
        "display": "6.2-inch OLED, 120 Hz",
        "camera_text": "50 MP wide + 13 MP ultrawide",
        "charging": "30W wired, 15W wireless",
    },
    {
        "brand": "Google",
        "name": "Pixel 7a",
        "slug": "google-pixel-7a",
        "summary": "Google's compact A-series phone with Tensor G2 and a 64 MP main camera.",
        "os": "Android 13",
        "ram": 8,
        "storage": 128,
        "battery": 4385,
        "refresh": 90,
        "chipset": "Google Tensor G2",
        "camera": 91,
        "gaming": 76,
        "battery_score": 78,
        "price": 499,
        "image": "https://placehold.co/600x800?text=Google+Pixel+7a",
        "display": "6.1-inch FHD+ OLED, up to 90 Hz",
        "camera_text": "64 MP wide + 13 MP ultrawide",
        "charging": "Fast wired charging, Qi wireless charging",
        "release_date": date(2023, 5, 10),
        "official_url": "https://support.google.com/pixelphone/answer/7158570",
    },
]


class Command(BaseCommand):
    help = "Create a small demo catalog for local development."

    def handle(self, *args, **options):
        for item in DEMO_DEVICES:
            brand, _ = Brand.objects.get_or_create(
                name=item["brand"], defaults={"slug": item["brand"].lower()}
            )
            device, _ = Device.objects.update_or_create(
                slug=item["slug"],
                defaults={
                    "brand": brand,
                    "name": item["name"],
                    "summary": item["summary"],
                    "operating_system": item["os"],
                    "release_date": item.get("release_date", date(2025, 1, 1)),
                    "status": Device.Status.AVAILABLE,
                    "primary_image_url": item["image"],
                    "official_url": item.get("official_url", ""),
                    "is_published": True,
                    "specifications": {"network": "5G", "water_resistance": "IP68"},
                },
            )
            DeviceImage.objects.update_or_create(
                device=device,
                image_url=item["image"],
                defaults={
                    "alt_text": f"{item['name']} front view",
                    "is_primary": True,
                    "sort_order": 0,
                },
            )
            specification_sections = [
                ("Network", [("Technology", "GSM / HSPA / LTE / 5G")]),
                (
                    "Platform",
                    [
                        ("OS", item["os"]),
                        ("Chipset", item["chipset"]),
                    ],
                ),
                ("Display", [("Type and size", item["display"])]),
                (
                    "Memory",
                    [
                        ("RAM", f"{item['ram']} GB"),
                        ("Internal storage", f"{item['storage']} GB"),
                    ],
                ),
                ("Main camera", [("Modules", item["camera_text"])]),
                (
                    "Battery",
                    [
                        ("Capacity", f"{item['battery']} mAh"),
                        ("Charging", item["charging"]),
                    ],
                ),
            ]
            for section_order, (section_name, section_items) in enumerate(
                specification_sections
            ):
                section, _ = SpecificationSection.objects.update_or_create(
                    device=device,
                    slug=slugify(section_name),
                    defaults={"name": section_name, "sort_order": section_order},
                )
                for item_order, (label, value) in enumerate(section_items):
                    SpecificationItem.objects.update_or_create(
                        section=section,
                        label=label,
                        defaults={"value": value, "sort_order": item_order},
                    )
            variant, _ = DeviceVariant.objects.update_or_create(
                device=device,
                name=f"{item['ram']}GB / {item['storage']}GB",
                defaults={
                    "ram_gb": item["ram"],
                    "storage_gb": item["storage"],
                    "battery_mah": item["battery"],
                    "display_refresh_hz": item["refresh"],
                    "chipset": item["chipset"],
                    "camera_score": item["camera"],
                    "gaming_score": item["gaming"],
                    "battery_score": item["battery_score"],
                },
            )
            MarketOffer.objects.update_or_create(
                variant=variant,
                country_code="US",
                seller_name="Demo Store",
                defaults={
                    "currency": "USD",
                    "price": item["price"],
                    "product_url": f"https://example.com/phones/{item['slug']}",
                },
            )
        self.stdout.write(self.style.SUCCESS("Demo catalog seeded."))
