"""Add GSMArena's exact official Pixel 5a 5G pictures to both 5a labels.

The two URLs are the actual 'official images' links on
https://www.gsmarena.com/google_pixel_5a_5g-pictures-11059.php
The catalog contains both Pixel 5a and Pixel 5a 5G, which refer to Google's
same 2021 device. This migration is additive and idempotent.
It never changes prices, variants, colors, or any other models.
"""
from django.db import migrations


SOURCE = "https://www.gsmarena.com/google_pixel_5a_5g-pictures-11059.php"
PICTURES = (
    "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-5a-5g-00.jpg",
    "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-5a-5g-01.jpg",
)


def add_pixel_5a_official_pictures(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Image = apps.get_model("catalog", "DeviceImage")
    inserted = 0
    updated = 0
    for name in ("Pixel 5a", "Pixel 5a 5G"):
        phone = Device.objects.filter(
            is_published=True, brand__name__iexact="Google",
            name__iexact=name,
        ).first()
        if not phone:
            continue
        if phone.primary_image_url or Image.objects.filter(device_id=phone.pk).exists():
            # Preserve an image if a later process already populated the phone.
            continue
        for index, url in enumerate(PICTURES):
            Image.objects.create(
                device_id=phone.pk, image_url=url,
                is_primary=index == 0, sort_order=index,
                view="unspecified",
                alt_text=f"Google {name} official product picture from GSMArena"[:200],
            )
            inserted += 1
        specs = dict(phone.specifications or {})
        specs["photo_attribution"] = {
            "publisher": "GSMArena",
            "source": SOURCE,
            "reuse_basis": "permission confirmed by Phone Discover operator",
            "note": "Pixel 5a and Pixel 5a 5G are the same marketed Google device.",
        }
        phone.primary_image_url = PICTURES[0]
        phone.specifications = specs
        phone.save(update_fields=["primary_image_url", "specifications", "updated_at"])
        updated += 1
    print(f"Pixel 5a photos: {updated} devices and {inserted} GSMArena picture links.", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0023_pixel_10_professional_product_renders")]
    operations = [migrations.RunPython(add_pixel_5a_official_pictures, migrations.RunPython.noop)]
