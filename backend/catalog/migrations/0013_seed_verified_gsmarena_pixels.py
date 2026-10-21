"""Seed independently checked GSMArena Pixel photographs from exact gallery links.

Phone Discover operator confirmed permission for GSMArena images.
Image URLs were taken from Google Pixel 5, 9, 9 Pro XL GSMArena
official pictures pages. Do not infer a Pro/Fold image from a base model.
Only add primary pictures to existing models without any photo.
"""
from django.db import migrations


VERIFIED = (
    ("Pixel 5", "https://www.gsmarena.com/google_pixel_5-pictures-10386.php",
     "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-5-5g-1.jpg"),
    ("Pixel 9", "https://www.gsmarena.com/google_pixel_9-pictures-13219.php",
     "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-9-1.jpg"),
    ("Pixel 9 Pro XL", "https://www.gsmarena.com/google_pixel_9_pro_xl-pictures-13217.php",
     "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-9-pro-xl-1.jpg"),
)


def seed_google_photos(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Image = apps.get_model("catalog", "DeviceImage")
    added = 0
    for name, source_page, image_url in VERIFIED:
        d = Device.objects.filter(is_published=True, brand__name__iexact="Google",
                                  name__iexact=name).first()
        if d is None or d.primary_image_url or Image.objects.filter(device_id=d.pk).exists():
            continue
        Image.objects.create(
            device_id=d.pk, image_url=image_url,
            alt_text=f"Google {name} official GSMArena gallery photo",
            view="unspecified", is_primary=True,
        )
        specs = dict(d.specifications or {})
        specs["photo_attribution"] = {
            "source": source_page,
            "publisher": "GSMArena",
            "reuse_basis": "permission confirmed by Phone Discover operator",
        }
        d.primary_image_url = image_url
        d.specifications = specs
        d.save(update_fields=["primary_image_url", "specifications", "updated_at"])
        added += 1
    print(f"Added {added} source-verified Google Pixel photos; preserved all existing images and prices.", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0012_import_cc_licensed_phone_photos")]
    operations = [migrations.RunPython(seed_google_photos, migrations.RunPython.noop)]
