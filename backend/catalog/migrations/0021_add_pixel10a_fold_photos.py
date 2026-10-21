"""Add exact-model licensed Pixel 10a diagrams and genuine Pixel Fold photo.

All Commons source files and authors were checked individually. These
entries fill only images that are currently absent, never prices, variants
or product identity. SVG illustrations are labeled illustrations.
"""
from django.db import migrations
from hashlib import md5
from urllib.parse import quote


# filename, author, media type, view
PHOTOS = {
    "Pixel 10a": (
        ("Google Pixel 10a (Obsidian, back).svg", "Mliu92", "illustration", "back"),
        ("Google Pixel 10a (Obsidian, front).svg", "Mliu92", "illustration", "front"),
    ),
    "Pixel Fold": (
        ("PixelFold.jpg", "PopePompus", "photograph", "unspecified"),
    ),
}
LICENSE = "https://creativecommons.org/licenses/by-sa/4.0/"


def commons_original_url(filename):
    sanitized = filename.replace(" ", "_")
    digest = md5(sanitized.encode("utf-8")).hexdigest()
    return (
        "https://upload.wikimedia.org/wikipedia/commons/"
        + digest[0] + "/" + digest[:2] + "/"
        + quote(sanitized, safe="()")
    )


def add_only_missing(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Image = apps.get_model("catalog", "DeviceImage")
    created = 0
    published = 0
    for device_name, files in PHOTOS.items():
        device = Device.objects.filter(
            is_published=True,
            brand__name__iexact="Google",
            name__iexact=device_name,
        ).first()
        if device is None:
            continue
        # Never change a phone with existing photography or gallery content.
        if device.primary_image_url or Image.objects.filter(device_id=device.pk).exists():
            continue
        primary_meta = None
        for index, (filename, author, media_type, view) in enumerate(files):
            url = commons_original_url(filename)
            Image.objects.create(
                device_id=device.pk,
                image_url=url,
                is_primary=index == 0,
                sort_order=index,
                alt_text=(f"Google {device_name} {view} "
                          f"{media_type} by {author}")[:200],
                view=view,
            )
            created += 1
            if index == 0:
                primary_meta = {
                    "source": "https://commons.wikimedia.org/wiki/File:"
                              + filename.replace(" ", "_"),
                    "publisher": "Wikimedia Commons",
                    "license": "CC BY-SA 4.0", "license_url": LICENSE,
                    "credit": author, "media_type": media_type,
                }
                device.primary_image_url = url
        specs = dict(device.specifications or {})
        specs["photo_attribution"] = primary_meta
        device.specifications = specs
        device.save(update_fields=["primary_image_url", "specifications", "updated_at"])
        published += 1
    print(
        f"Pixel 10a/Fold backfill: {published} previously missing phones, "
        f"{created} new licensed visuals; all prices/variants unchanged.",
        flush=True,
    )


class Migration(migrations.Migration):
    dependencies = [("catalog", "0020_fill_exact_pixel_5g_alias_photos")]
    operations = [migrations.RunPython(add_only_missing, migrations.RunPython.noop)]
