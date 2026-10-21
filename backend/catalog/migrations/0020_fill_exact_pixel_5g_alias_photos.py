"""Fill missing photos on Pixel models duplicated with an explicit '5G' suffix.

These five base Pixel models have 5G modems as documented by GSMArena.
The source and target are the same manufacturer's base model, not a Pro,
XL, Fold or regional-spec substitution. Only media is duplicated;
existing model/variant/price records are kept independent and unchanged.
"""
from django.db import migrations


BASE_TO_5G_ALIAS = (
    ("Pixel 6", "Pixel 6 5G"),
    ("Pixel 7", "Pixel 7 5G"),
    ("Pixel 7 Pro", "Pixel 7 Pro 5G"),
    ("Pixel 8", "Pixel 8 5G"),
    ("Pixel 10", "Pixel 10 5G"),
)


def copy_exact_model_5g_media(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Image = apps.get_model("catalog", "DeviceImage")
    copied_models = 0
    copied_images = 0
    for base_name, name_5g in BASE_TO_5G_ALIAS:
        base = Device.objects.filter(
            brand__name__iexact="Google", name__iexact=base_name,
            is_published=True,
        ).first()
        alias = Device.objects.filter(
            brand__name__iexact="Google", name__iexact=name_5g,
            is_published=True,
        ).first()
        if not base or not alias or not base.primary_image_url or alias.primary_image_url:
            continue
        if Image.objects.filter(device_id=alias.pk).exists():
            # Do not alter an alias with existing photography.
            continue

        base_images = list(Image.objects.filter(device_id=base.pk)
                           .order_by("-is_primary", "sort_order", "id"))
        # Preserve the primary and a few real product views, but do not
        # propagate unrelated sketches if the base has verified photos.
        product_images = [
            image for image in base_images if
            image.image_url == base.primary_image_url or
            "gsmarena.com/vv/pics/google/" in image.image_url
        ][:4]
        if not product_images:
            continue

        if not any(img.image_url == base.primary_image_url for img in product_images):
            continue
        for order, pic in enumerate(product_images):
            Image.objects.create(
                device_id=alias.pk, image_url=pic.image_url,
                view=pic.view,
                alt_text=(f"Google {name_5g} same base-model {pic.view} view")[:200],
                is_primary=pic.image_url == base.primary_image_url,
                sort_order=order,
            )
            copied_images += 1
        attribution = dict((base.specifications or {}).get("photo_attribution") or {})
        details = dict(alias.specifications or {})
        if attribution and not details.get("photo_attribution"):
            details["photo_attribution"] = attribution
        details["product_image_equivalent_model"] = base_name
        details["product_image_alias_basis"] = (
            "Manufacturer's base model supports 5G; the '5G' catalog suffix "
            "does not change the phone's product appearance."
        )
        alias.specifications = details
        alias.primary_image_url = base.primary_image_url
        alias.save(update_fields=["specifications", "primary_image_url", "updated_at"])
        copied_models += 1

    print(f"5G-label Pixel image coverage: {copied_models} previously blank "
          f"catalog identities and {copied_images} correct same-model images filled. "
          "No prices, RAM/storage variants, or phone names changed.", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0019_import_verified_gsmarena_pixel_images")]
    operations = [migrations.RunPython(copy_exact_model_5g_media, migrations.RunPython.noop)]
