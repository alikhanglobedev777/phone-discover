"""Add exactly identified, reusable photos to previously image-less Google Pixels.

Sources are Wikimedia Commons original photographs (not camera samples).
Image/title, author, and CC license were checked on each linked file page.
This migration is additive: it does not replace existing product images,
prices, variants, colors, specifications, or phone records.
"""
from django.db import migrations


# (url, Commons description page, license, author, actual view)
PHOTOS = {
    "Pixel 6a": (
        (
            "https://upload.wikimedia.org/wikipedia/commons/thumb/3/37/Google_Pixel_6a_back.jpg/500px-Google_Pixel_6a_back.jpg",
            "https://commons.wikimedia.org/wiki/File:Google_Pixel_6a_back.jpg",
            "CC BY-SA 4.0", "Nisiguti", "back",
        ),
        (
            "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cc/Google_Pixel_6a_front.jpg/500px-Google_Pixel_6a_front.jpg",
            "https://commons.wikimedia.org/wiki/File:Google_Pixel_6a_front.jpg",
            "CC BY-SA 4.0", "Nisiguti", "front",
        ),
    ),
    "Pixel 8A": (
        (
            "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Rear_view_of_Pixel_8a.jpg/500px-Rear_view_of_Pixel_8a.jpg",
            "https://commons.wikimedia.org/wiki/File:Rear_view_of_Pixel_8a.jpg",
            "CC BY 4.0", "Miyako Fujimiya", "back",
        ),
    ),
    "Pixel 7": (
        (
            "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b0/Google_Pixel_7_20230416_HOF00365_RAW-Export.png/960px-Google_Pixel_7_20230416_HOF00365_RAW-Export.png",
            "https://commons.wikimedia.org/wiki/File:Google_Pixel_7_20230416_HOF00365_RAW-Export.png",
            "CC BY 4.0", "PantheraLeo1359531", "back",
        ),
    ),
}


def add_verified_photographs(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Image = apps.get_model("catalog", "DeviceImage")
    added = 0
    new_primary = 0
    for name, records in PHOTOS.items():
        device = Device.objects.filter(
            brand__name__iexact="Google",
            name__iexact=name,
            is_published=True,
        ).first()
        if device is None:
            continue
        has_primary = bool(device.primary_image_url)
        existing = set(Image.objects.filter(device_id=device.pk).values_list("image_url", flat=True))
        for index, (url, source, license_name, author, view) in enumerate(records):
            if url in existing:
                continue
            is_primary = not has_primary and not existing
            Image.objects.create(
                device_id=device.pk,
                image_url=url,
                view=view,
                is_primary=is_primary,
                sort_order=30 + index,
                alt_text=f"Google {name} {view} photograph by {author}"[:200],
            )
            added += 1
            existing.add(url)
            if is_primary:
                specs = dict(device.specifications or {})
                specs["photo_attribution"] = {
                    "source": source, "license": license_name,
                    "license_url": "https://creativecommons.org/licenses/by-sa/4.0/"
                    if license_name == "CC BY-SA 4.0"
                    else "https://creativecommons.org/licenses/by/4.0/",
                    "credit": author,
                    "publisher": "Wikimedia Commons",
                }
                device.primary_image_url = url
                device.specifications = specs
                device.save(update_fields=["primary_image_url", "specifications", "updated_at"])
                has_primary = True
                new_primary += 1
    print(f"Verified Pixel photo backfill: {added} additional photos, "
          f"{new_primary} new primary images. Existing prices and media preserved.", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0015_more_gsmarena_pixel_gallery_photos")]
    operations = [migrations.RunPython(add_verified_photographs, migrations.RunPython.noop)]
