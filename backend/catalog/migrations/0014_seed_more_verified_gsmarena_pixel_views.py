"""Add only image URLs verified on exact GSMArena Pixel picture galleries.

Includes an additional catalog model and second documented views for Pixel 9
and 9 Pro XL. No color-specific view claims and no price or variant changes.
"""
from django.db import migrations


PHOTOS = {
    "Pixel 7 Pro": (
        ("https://www.gsmarena.com/google_pixel_7_pro-pictures-11908.php",
         "https://fdn2.gsmarena.com/vv/pics/google/google-pixel7-pro-2.jpg"),
        ("https://www.gsmarena.com/google_pixel_7_pro-pictures-11908.php",
         "https://fdn2.gsmarena.com/vv/pics/google/google-pixel7-pro-3.jpg"),
    ),
    "Pixel 9": (
        ("https://www.gsmarena.com/google_pixel_9-pictures-13219.php",
         "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-9-2.jpg"),
    ),
    "Pixel 9 Pro XL": (
        ("https://www.gsmarena.com/google_pixel_9_pro_xl-pictures-13217.php",
         "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-9-pro-xl-2.jpg"),
    ),
}


def add_verified_views(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Image = apps.get_model("catalog", "DeviceImage")
    created = 0
    for name, entries in PHOTOS.items():
        device = Device.objects.filter(
            brand__name__iexact="Google", name__iexact=name,
            is_published=True,
        ).first()
        if device is None:
            continue
        has_primary = bool(device.primary_image_url)
        for order, (source, url) in enumerate(entries):
            image, added = Image.objects.get_or_create(
                device_id=device.pk, image_url=url,
                defaults={
                    "alt_text": f"Google {name} GSMArena gallery photograph",
                    "view": "unspecified",
                    "is_primary": not has_primary,
                    "sort_order": 20 + order,
                },
            )
            if added:
                created += 1
                if not has_primary:
                    device.primary_image_url = url
                    specs = dict(device.specifications or {})
                    specs["photo_attribution"] = {
                        "publisher": "GSMArena",
                        "source": source,
                        "reuse_basis": "permission confirmed by Phone Discover operator",
                    }
                    device.specifications = specs
                    device.save(update_fields=["primary_image_url", "specifications", "updated_at"])
                    has_primary = True
    print(f"Added {created} exact-model GSMArena Pixel gallery views", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0013_seed_verified_gsmarena_pixels")]
    operations = [migrations.RunPython(add_verified_views, migrations.RunPython.noop)]
