"""Correct unsuitable Pixel 7/8a imagery and fill a few blank cards.

Where GSMArena's official CDN cannot yet be validated, use truthful,
exact-model CC BY-SA 4.0 Wikimedia Commons *illustrations*, not fabricated
photographs. These are interim visuals. Existing real images are never
replaced except for the TWO specific photos the operator identified as
unsuitable. No phones, memory variants, prices or spec fields are touched.
"""
from django.db import migrations

LICENSE = "https://creativecommons.org/licenses/by-sa/4.0/"

# (Commons filename, photographer/artist, view). All are model-specific
# CC BY-SA 4.0 works, not arbitrary generic handset images.
VISUALS = {
    "Pixel 7": (
        ("Google Pixel 7 back (Obsidian).svg", "Mliu92", "back"),
        ("Google Pixel 7 front.svg", "Mliu92", "front"),
    ),
    "Pixel 8A": (
        ("Google Pixel 8a front.svg", "DM115Wiki", "front"),
    ),
    "Pixel 6": (
        ("Google Pixel 6 back (Stormy Black).svg", "Mliu92", "back"),
        ("Google Pixel 6 front.svg", "Mliu92", "front"),
    ),
    "Pixel 6 Pro": (
        ("Google Pixel 6 Pro back (Stormy Black).svg", "Mliu92", "back"),
        ("Google Pixel 6 Pro front.svg", "Mliu92", "front"),
    ),
    "Pixel 8": (
        ("Google Pixel 8 back (Obsidian).svg", "Mliu92", "back"),
        ("Google Pixel 8 front.svg", "Mliu92", "front"),
    ),
    "Pixel 10": (
        ("Pixel 10 back (Obsidian).svg", "Mliu92", "back"),
    ),
    "Pixel 10 Pro XL": (
        ("Pixel 10 Pro XL back (Obsidian).svg", "Mliu92", "back"),
    ),
}

# The only previously imported photographs explicitly identified as bad.
REMOVE = {
    "Pixel 7": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b0/Google_Pixel_7_20230416_HOF00365_RAW-Export.png/960px-Google_Pixel_7_20230416_HOF00365_RAW-Export.png",
    "Pixel 8A": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Rear_view_of_Pixel_8a.jpg/500px-Rear_view_of_Pixel_8a.jpg",
}


def commons_image_url(filename):
    import hashlib
    from urllib.parse import quote
    canonical = filename.replace(" ", "_")
    digest = hashlib.md5(canonical.encode("utf-8")).hexdigest()
    return (f"https://upload.wikimedia.org/wikipedia/commons/"
            f"{digest[0]}/{digest[:2]}/{quote(canonical, safe='()')}")


def enrich(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Image = apps.get_model("catalog", "DeviceImage")
    count = 0
    replaced = 0
    for name, pictures in VISUALS.items():
        device = Device.objects.filter(brand__name__iexact="Google",
                                       name__iexact=name, is_published=True).first()
        if device is None:
            continue
        old_url = REMOVE.get(name)
        if old_url and device.primary_image_url == old_url:
            Image.objects.filter(device_id=device.pk, image_url=old_url).delete()
            device.primary_image_url = ""
            replaced += 1

        # Other genuine images stay primary; illustrations don't replace them.
        existing_primary = bool(device.primary_image_url)
        if not existing_primary:
            existing_primary = Image.objects.filter(device_id=device.pk,
                                                    is_primary=True).exists()

        primary_attribution = None
        for order, (filename, artist, view) in enumerate(pictures):
            url = commons_image_url(filename)
            if Image.objects.filter(device_id=device.pk, image_url=url).exists():
                continue
            is_primary = not existing_primary
            Image.objects.create(
                device_id=device.pk, image_url=url, view=view,
                sort_order=40 + order, is_primary=is_primary,
                alt_text=f"Google {name} {view} illustration by {artist}"[:200],
            )
            count += 1
            if is_primary:
                existing_primary = True
                device.primary_image_url = url
                primary_attribution = {
                    "source": "https://commons.wikimedia.org/wiki/File:" +
                              filename.replace(" ", "_"),
                    "license": "CC BY-SA 4.0", "license_url": LICENSE,
                    "credit": artist, "publisher": "Wikimedia Commons",
                    "media_type": "model-specific illustration (not photograph)",
                }

        if primary_attribution:
            specs = dict(device.specifications or {})
            specs["photo_attribution"] = primary_attribution
            device.specifications = specs
            device.save(update_fields=["primary_image_url", "specifications", "updated_at"])
        elif old_url and device.primary_image_url == "":
            # If another verified image existed as a nonprimary record,
            # restore that instead of leaving a stale deleted URL.
            existing = Image.objects.filter(device_id=device.pk).order_by("id").first()
            if existing:
                existing.is_primary = True
                existing.save(update_fields=["is_primary"])
                device.primary_image_url = existing.image_url
                device.save(update_fields=["primary_image_url", "updated_at"])

    print(f"Pixel visual cleanup: {replaced} unsuitable primary photos replaced, "
          f"{count} exact-model licensed device illustrations attached.", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0017_add_verified_pixel_9a_and_fold_photos")]
    operations = [migrations.RunPython(enrich, migrations.RunPython.noop)]
