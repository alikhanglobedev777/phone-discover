"""Add genuine, exact-model Wikimedia photos for Pixel 9a and 10 Pro Fold.

Both filenames and CC licenses were checked on their Commons file pages.
The thumbnail paths use Wikimedia's deterministic MD5 file-name directory
convention; avoid assigning a Fold or Pro image to a different model.
Only missing primary images are filled. Prices/variants never change.
"""
from django.db import migrations

VERIFIED = {
    "Pixel 9A": (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cc/Pixel_9a_back.jpg/500px-Pixel_9a_back.jpg",
        "https://commons.wikimedia.org/wiki/File:Pixel_9a_back.jpg",
        "CC BY 4.0", "Maksdroider", "back",
    ),
    "Pixel 10 Pro Fold": (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/1/12/Pixel10ProFold.png/960px-Pixel10ProFold.png",
        "https://commons.wikimedia.org/wiki/File:Pixel10ProFold.png",
        "CC BY-SA 4.0", "YCVn", "unspecified",
    ),
}


def add_pixel_photos(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Image = apps.get_model("catalog", "DeviceImage")
    created = 0
    for name, (url, source, license_name, author, view) in VERIFIED.items():
        device = Device.objects.filter(
            is_published=True, brand__name__iexact="Google",
            name__iexact=name,
        ).first()
        if device is None:
            continue
        if Image.objects.filter(device_id=device.pk, image_url=url).exists():
            continue
        use_primary = (
            not device.primary_image_url and
            not Image.objects.filter(device_id=device.pk, is_primary=True).exists()
        )
        Image.objects.create(
            device_id=device.pk, image_url=url,
            is_primary=use_primary, view=view, sort_order=30,
            alt_text=f"Google {name} photograph by {author}"[:200],
        )
        created += 1
        if use_primary:
            specs = dict(device.specifications or {})
            specs["photo_attribution"] = {
                "source": source,
                "publisher": "Wikimedia Commons",
                "credit": author,
                "license": license_name,
                "license_url": "https://creativecommons.org/licenses/by-sa/4.0/"
                if license_name == "CC BY-SA 4.0"
                else "https://creativecommons.org/licenses/by/4.0/",
            }
            device.primary_image_url = url
            device.specifications = specs
            device.save(update_fields=["primary_image_url", "specifications", "updated_at"])
    print(f"Pixel 9a/Fold photo enrichment: {created} verified photographs added.", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0016_add_verified_pixel_photographs")]
    operations = [migrations.RunPython(add_pixel_photos, migrations.RunPython.noop)]
