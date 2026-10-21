"""Additional exactly matched Google Pixel GSMArena gallery links.

Photo URLs retrieved from the model's official pictures page, not inferred
from naming patterns. Operator-approved reuse. Create-only, preserve all
existing photos, prices, RAM/storage variants and device fields.
"""
from django.db import migrations

PHOTOS = {
    "Pixel 4a": (
        ("https://www.gsmarena.com/google_pixel_4a-pictures-10123.php",
         "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-4a-1.jpg"),
        ("https://www.gsmarena.com/google_pixel_4a-pictures-10123.php",
         "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-4a-3.jpg"),
    ),
    "Pixel 8 Pro": (
        ("https://www.gsmarena.com/google_pixel_8_pro-pictures-12545.php",
         "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-8-pro-1.jpg"),
        ("https://www.gsmarena.com/google_pixel_8_pro-pictures-12545.php",
         "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-8-pro-2.jpg"),
    ),
}


def add_exact_images(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Image = apps.get_model("catalog", "DeviceImage")
    added = 0
    for name, items in PHOTOS.items():
        device = Device.objects.filter(is_published=True,
            brand__name__iexact="Google", name__iexact=name).first()
        if not device:
            continue
        primary_exists = bool(device.primary_image_url) or Image.objects.filter(
            device_id=device.pk, is_primary=True).exists()
        for index, (source, url) in enumerate(items):
            if Image.objects.filter(device_id=device.pk, image_url=url).exists():
                continue
            is_primary = not primary_exists
            Image.objects.create(device_id=device.pk, image_url=url,
                view="unspecified", is_primary=is_primary, sort_order=20 + index,
                alt_text=f"Google {name} product gallery photo from GSMArena")
            added += 1
            if is_primary:
                device.primary_image_url = url
                specs = dict(device.specifications or {})
                specs["photo_attribution"] = {
                    "publisher": "GSMArena",
                    "source": source,
                    "reuse_basis": "permission confirmed by Phone Discover operator",
                }
                device.specifications = specs
                device.save(update_fields=["primary_image_url", "specifications", "updated_at"])
                primary_exists = True
    print(f"Added {added} verified additional Google Pixel gallery views", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0014_seed_more_verified_gsmarena_pixel_views")]
    operations = [migrations.RunPython(add_exact_images, migrations.RunPython.noop)]
