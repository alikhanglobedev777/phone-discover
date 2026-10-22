"""Fill two storage-only iPhone cards from the same photographed base phone.

The 1 TB model is the same physical iPhone as its already-pictured base model.
No size, generation, Pro/Max, or SIM-network naming substitutions are made.
Only currently empty photo records are updated. Prices, variants untouched.
"""
from django.db import migrations

STORAGE_EQUIVALENTS = (
    ("iPhone 15 Pro Max", "iPhone 15 Pro Max (1TB)"),
    ("iPhone 16 Pro Max", "iPhone 16 Pro Max (1TB SG)"),
)


def copy_identical_phone_photos(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Image = apps.get_model("catalog", "DeviceImage")
    filled = 0
    for base_name, storage_name in STORAGE_EQUIVALENTS:
        original = Device.objects.filter(
            brand__name__iexact="Apple", name__iexact=base_name,
            is_published=True,
        ).first()
        target = Device.objects.filter(
            brand__name__iexact="Apple", name__iexact=storage_name,
            is_published=True,
        ).first()
        if not original or not target or not original.primary_image_url:
            continue
        if target.primary_image_url or Image.objects.filter(device_id=target.pk).exists():
            continue

        original_gallery = list(Image.objects.filter(
            device_id=original.pk).order_by("-is_primary", "sort_order", "id"))
        if not any(image.image_url == original.primary_image_url
                   for image in original_gallery):
            continue
        for index, photo in enumerate(original_gallery[:4]):
            Image.objects.create(
                device_id=target.pk,
                image_url=photo.image_url,
                view=photo.view,
                is_primary=(photo.image_url == original.primary_image_url),
                sort_order=index,
                alt_text=(f"Apple {storage_name} product image, identical exterior "
                          f"to {base_name}")[:200],
            )
        specifications = dict(target.specifications or {})
        provenance = dict((original.specifications or {}).get("photo_attribution") or {})
        provenance["representative_for"] = base_name
        provenance["equivalence_basis"] = "Same model, storage-only edition"
        specifications["photo_attribution"] = provenance
        target.specifications = specifications
        target.primary_image_url = original.primary_image_url
        target.save(update_fields=["primary_image_url", "specifications", "updated_at"])
        filled += 1

    print(f"Same-model iPhone storage imagery: {filled} missing cards filled", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0028_backfill_exact_manufacturer_images")]
    operations = [migrations.RunPython(copy_identical_phone_photos, migrations.RunPython.noop)]
