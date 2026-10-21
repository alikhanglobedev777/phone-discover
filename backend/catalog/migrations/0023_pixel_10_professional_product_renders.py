"""Promote exact-model professional studio renders for Pixel 10 Pro/Fold.

The primary image is a manufacturer-style retail product render of the
specified device. Sources are the publishing retailers' product pages, with
an image URL that was independently matched to the same model.
Previously recorded photographs/illustrations are retained as secondary
gallery images. No changes to price, variants, specs, colors or identity.
"""
from django.db import migrations


RENDERS = {
    "Pixel 10 Pro": {
        "image": (
            "https://www.au.com/adobe/dynamicmedia/deliver/"
            "dm-aid--92d7fa66-8387-4e31-b7b4-0e006b020f58/"
            "pixel10p_moonstone_01_d92aceb2690e766f.jpg"
            "?preferwebp=true&quality=90"
        ),
        "page": "https://www.au.com/mobile/product/smartphone/pixel10p/",
        "publisher": "au / KDDI",
        "finish": "Moonstone",
        "alt": "Google Pixel 10 Pro Moonstone, official-style front and rear studio render",
    },
    "Pixel 10 Pro Fold": {
        "image": (
            "https://www.visible.com/shop/assets/images/shop/"
            "Pixel10ProFold-Moonstone-Front.jpg"
        ),
        "page": "https://www.visible.com/shop/smartphones/google-pixel-10-pro-fold",
        "publisher": "Visible",
        "finish": "Moonstone",
        "alt": "Google Pixel 10 Pro Fold Moonstone, front and rear studio product render",
    },
}


def promote_professional_images(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    DeviceImage = apps.get_model("catalog", "DeviceImage")
    updated = 0
    for model_name, asset in RENDERS.items():
        # Only update the exact intended product. No nearest-model matching.
        device = Device.objects.filter(
            brand__name__iexact="Google",
            name__iexact=model_name,
            is_published=True,
        ).first()
        if device is None:
            continue

        image_url = asset["image"]
        # Keep all existing images, but only one primary gallery image.
        DeviceImage.objects.filter(device_id=device.pk, is_primary=True).exclude(
            image_url=image_url
        ).update(is_primary=False)

        product_image, created = DeviceImage.objects.get_or_create(
            device_id=device.pk,
            image_url=image_url,
            defaults={
                "view": "unspecified",
                "is_primary": True,
                "sort_order": 0,
                "alt_text": asset["alt"][:200],
            },
        )
        if not created:
            product_image.is_primary = True
            product_image.sort_order = 0
            product_image.alt_text = asset["alt"][:200]
            product_image.save(update_fields=["is_primary", "sort_order", "alt_text"])

        if device.primary_image_url != image_url:
            specs = dict(device.specifications or {})
            previous_attribution = specs.get("photo_attribution")
            if previous_attribution and previous_attribution != {
                "source": asset["page"], "publisher": asset["publisher"]
            }:
                historical = list(specs.get("previous_photo_attributions") or [])
                if previous_attribution not in historical:
                    historical.append(previous_attribution)
                specs["previous_photo_attributions"] = historical
            specs["photo_attribution"] = {
                "source": asset["page"],
                "publisher": asset["publisher"],
                "media_type": "professional studio product render",
                "finish": asset["finish"],
                "source_image_url": image_url,
            }
            device.primary_image_url = image_url
            device.specifications = specs
            device.save(update_fields=[
                "primary_image_url", "specifications", "updated_at",
            ])
            updated += 1

    print(
        f"Pixel 10 Pro/Fold studio-image update: {updated} primary photos "
        "upgraded. Older gallery images, prices and variants preserved.",
        flush=True,
    )


class Migration(migrations.Migration):
    dependencies = [("catalog", "0022_import_remaining_verified_pixel_photos")]
    operations = [migrations.RunPython(
        promote_professional_images, migrations.RunPython.noop
    )]
