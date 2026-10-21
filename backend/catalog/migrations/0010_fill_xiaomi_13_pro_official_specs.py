"""Fill verified Xiaomi 13 Pro details from manufacturer's published spec sheet.

Source: https://www.mi.com/global/product/xiaomi-13-pro/specs/
Only missing data is populated. Do not change model names, RAM/storage,
existing photos, observed Pakistan prices, or preexisting specification values.
"""
from django.db import migrations

SOURCE = "https://www.mi.com/global/product/xiaomi-13-pro/specs/"
SECTIONS = (
    ("Display", (("Panel", '6.73-inch WQHD+ AMOLED, LTPO'), ("Resolution", "3200 × 1440"),
                 ("Refresh rate", "Adaptive 1–120 Hz"), ("Protection", "Gorilla Glass Victus"))),
    ("Cameras", (("Main", '50 MP Leica 1-inch main sensor (IMX989), HyperOIS'),
                 ("Telephoto", "50 MP Leica 75 mm floating telephoto with OIS"),
                 ("Ultrawide", "50 MP Leica ultrawide, 115° field of view"),
                 ("Selfie", "32 MP front camera"))),
    ("Power", (("Battery", "4820 mAh (typical)"), ("Wired charging", "120 W HyperCharge"),
                ("Wireless charging", "50 W"), ("Reverse wireless", "10 W"))),
    ("Hardware", (("Processor", "Qualcomm Snapdragon 8 Gen 2 (4 nm)"),
                   ("Memory type", "LPDDR5X"), ("Storage type", "UFS 4.0"),
                   ("Water resistance", "IP68"), ("Audio", "Stereo speakers, Dolby Atmos"))),
    ("Software", (("Launch interface", "MIUI 14"),)),
)


def apply_official_specs(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Variant = apps.get_model("catalog", "DeviceVariant")
    Section = apps.get_model("catalog", "SpecificationSection")
    Item = apps.get_model("catalog", "SpecificationItem")
    device = Device.objects.filter(brand__name__iexact="Xiaomi",
                                   name__iexact="13 Pro").order_by("pk").first()
    if device is None:
        return

    if not device.operating_system:
        device.operating_system = "MIUI 14 (Android 13 at launch)"
        device.save(update_fields=["operating_system", "updated_at"])
    for v in Variant.objects.filter(device_id=device.pk):
        updates = []
        if not v.chipset:
            v.chipset = "Qualcomm Snapdragon 8 Gen 2"
            updates.append("chipset")
        if v.battery_mah is None:
            v.battery_mah = 4820
            updates.append("battery_mah")
        if v.display_refresh_hz is None:
            v.display_refresh_hz = 120
            updates.append("display_refresh_hz")
        if updates:
            v.save(update_fields=updates)

    for index, (name, pairs) in enumerate(SECTIONS):
        slug = name.casefold().replace(" ", "-")
        section, _ = Section.objects.get_or_create(
            device_id=device.pk, slug=slug,
            defaults={"name": name, "sort_order": index},
        )
        for order, (label, value) in enumerate(pairs):
            Item.objects.get_or_create(section_id=section.pk, label=label,
                                       defaults={"value": value, "sort_order": order})
    specs = dict(device.specifications or {})
    attribution = dict(specs.get("catalog_attribution") or {})
    refs = set(attribution.get("source_urls") or [])
    refs.add(SOURCE)
    attribution["source_urls"] = sorted(refs)
    specs["catalog_attribution"] = attribution
    specs["manufacturer_verified_specifications_url"] = SOURCE
    device.specifications = specs
    device.save(update_fields=["specifications", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [("catalog", "0009_import_whatmobile_media")]
    operations = [migrations.RunPython(apply_official_specs, migrations.RunPython.noop)]
