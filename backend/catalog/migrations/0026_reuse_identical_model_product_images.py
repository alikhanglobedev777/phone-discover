"""Fill image-less variant-label rows from an already photographed SAME phone.

Only cosmetic name spelling, explicitly memory-only parenthetical labels, and
US 'UW' network labels on iPhones are mapped. These have the same marketed
base-model exterior; the carrier SKU can differ in antenna details, so
image provenance labels it as a representative base-model photo.

NEVER merge device records, edit variant RAM/storage, change prices, copy a
Pro/Max/Fold image to another model, infer an LTE/5G hardware equivalent, or
replace existing photos. Regions without memory-only labels are skipped.
"""
import re
from django.db import migrations

STORAGE_ONLY = re.compile(
    r"^(?P<base>.+?)\s+\((?P<memory>\d{2,4}(?:GB|TB))"
    r"(?:\s+(?:USA|US|SG|UK|EU|PK))?\)$",
    re.IGNORECASE,
)
APPLE_UW = re.compile(r"^(iPhone (?:12|13|14)(?: .+?)?) UW$", re.IGNORECASE)


def simplified(value):
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def eligible_base(brand, name):
    storage = STORAGE_ONLY.fullmatch(name)
    if storage:
        return storage.group("base"), "storage and market label"
    if brand.casefold() == "apple":
        uw = APPLE_UW.fullmatch(name)
        if uw:
            return uw.group(1), "US ultra-wideband carrier label (representative exterior)"
    return None


def add_matching_images(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Image = apps.get_model("catalog", "DeviceImage")
    phones = list(Device.objects.select_related("brand").filter(is_published=True))
    by_exact = {}
    by_simplified = {}
    for device in phones:
        brand = device.brand.name.casefold()
        by_exact.setdefault((brand, device.name.casefold()), []).append(device)
        by_simplified.setdefault((brand, simplified(device.name)), []).append(device)

    known_images = {}
    for im in Image.objects.all().iterator():
        known_images.setdefault(im.device_id, []).append(im)
    filled = 0
    images_added = 0
    for device in phones:
        if device.primary_image_url or known_images.get(device.pk):
            continue
        brand = device.brand.name.casefold()
        match = eligible_base(brand, device.name)
        if match:
            base_name, equivalence = match
            candidates = by_exact.get((brand, base_name.casefold()), [])
            if not candidates:
                candidates = by_simplified.get((brand, simplified(base_name)), [])
        else:
            equivalence = "equivalent name spelling only"
            candidates = by_simplified.get((brand, simplified(device.name)), [])
            candidates = [c for c in candidates if c.pk != device.pk]
        candidates = [c for c in candidates if c.primary_image_url]
        # Never select one of multiple plausible sources arbitrarily.
        source_urls = {c.primary_image_url for c in candidates}
        if len(source_urls) != 1:
            continue
        source = min(candidates, key=lambda d: d.pk)
        if source.pk == device.pk:
            continue
        gallery = [
            im for im in known_images.get(source.pk, [])
            if im.image_url == source.primary_image_url
        ]
        if not gallery:
            continue
        # Identity must not inadvertently collapse other generation numbers.
        if simplified(source.name) == simplified(device.name):
            equivalence = "equivalent name spelling only"
        elif not match:
            continue
        for src_image in gallery[:1]:
            Image.objects.create(
                device_id=device.pk, image_url=src_image.image_url,
                view=src_image.view, is_primary=True, sort_order=0,
                alt_text=(f"{device.brand.name} {device.name} representative "
                          f"product view; same marketed model as {source.name}")[:200],
            )
            images_added += 1

        specs = dict(device.specifications or {})
        src_specs = dict(source.specifications or {})
        specs["photo_attribution"] = {
            **dict(src_specs.get("photo_attribution") or {}),
            "representative_for": source.name,
            "equivalence_basis": equivalence,
            "note": "Reference photo is of the same base phone; memory/carrier editions "
                    "may have minor regional appearance differences.",
        }
        device.primary_image_url = source.primary_image_url
        device.specifications = specs
        device.save(update_fields=["primary_image_url", "specifications", "updated_at"])
        filled += 1
    print(f"Identical-model label photo reuse: {filled} newly pictured phones, "
          f"{images_added} source-backed image entries. "
          "No prices, variants, specs or existing images overwritten.", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0025_backfill_verified_all_brand_images")]
    operations = [migrations.RunPython(add_matching_images, migrations.RunPython.noop)]
