"""Add three hand-verified, freely licensed Xiaomi phone photos.

Only exact base models are affected. No invented assets, name matching beyond
brand+model, or edits to existing photos, variants, prices, or other devices.
Files and attribution: Wikimedia Commons, CC BY-SA 4.0, photographer 洛微.
"""
from django.db import migrations


PHOTOS = (
    ("12", "https://upload.wikimedia.org/wikipedia/commons/3/3d/The_back_of_Xiaomi_12.jpg",
     "https://commons.wikimedia.org/wiki/File:The_back_of_Xiaomi_12.jpg"),
    ("12S", "https://upload.wikimedia.org/wikipedia/commons/4/4f/The_back_of_Xiaomi_12S.jpg",
     "https://commons.wikimedia.org/wiki/File:The_back_of_Xiaomi_12S.jpg"),
    ("12S Ultra", "https://upload.wikimedia.org/wikipedia/commons/1/16/The_back_of_Xiaomi_12SU.jpg",
     "https://commons.wikimedia.org/wiki/File:The_back_of_Xiaomi_12SU.jpg"),
)


def seed_verified_photos(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    DeviceImage = apps.get_model("catalog", "DeviceImage")
    for name, image_url, source_url in PHOTOS:
        device = (Device.objects.filter(brand__name__iexact="Xiaomi", name__iexact=name)
                  .order_by("pk").first())
        if not device or device.primary_image_url or DeviceImage.objects.filter(device=device).exists():
            continue
        DeviceImage.objects.create(
            device=device, image_url=image_url,
            alt_text=f"Xiaomi {name} rear product photo", is_primary=True,
            view="back",
        )
        specs = dict(device.specifications or {})
        specs["photo_attribution"] = {
            "source": source_url,
            "license": "CC BY-SA 4.0",
            "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            "credit": "洛微",
        }
        device.specifications = specs
        device.primary_image_url = image_url
        device.save(update_fields=["primary_image_url", "specifications", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0007_price_refresh_runs")]
    operations = [migrations.RunPython(seed_verified_photos, migrations.RunPython.noop)]
