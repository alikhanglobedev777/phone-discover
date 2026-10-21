"""Expose existing, recorded variant facts in structured detail sections for all phones.

Existing data only: no guesses, prices, scores, identity merges or changes
to variant fields. Source is marked 'Recorded catalog data', not manufacturer
verified. WhatMobile enrichment (separate migration 0012) adds sourced detail.
"""
from django.db import migrations


def populate_existing_sections(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Section = apps.get_model("catalog", "SpecificationSection")
    Item = apps.get_model("catalog", "SpecificationItem")
    seen = set(Section.objects.values_list("device_id", "slug"))
    existing = set(Item.objects.values_list("section_id", "label"))
    new_sections = []
    facts_by_device = {}
    for device in Device.objects.filter(is_published=True).prefetch_related("variants"):
        versions = list(device.variants.all())
        facts = []
        memory = sorted({(v.ram_gb, v.storage_gb) for v in versions})
        if memory:
            pairs = ", ".join(f"{ram} GB RAM / {storage} GB storage"
                              for ram, storage in memory)
            # Avoid very long or malformed values; the variant selector
            # remains the authoritative list for unusually many configurations.
            if len(pairs) <= 800:
                facts.append(("Recorded configurations", pairs))
        if device.operating_system:
            facts.append(("Operating system (recorded)", device.operating_system))
        for label, field, unit in (
            ("Chipset (recorded)", "chipset", ""),
            ("Battery capacity (recorded)", "battery_mah", " mAh"),
            ("Display refresh (recorded)", "display_refresh_hz", " Hz"),
        ):
            values = {getattr(v, field) for v in versions if getattr(v, field)}
            if len(values) == 1:
                facts.append((label, f"{next(iter(values))}{unit}"))
        if not facts:
            continue
        key = (device.pk, "recorded-catalog-data")
        if key not in seen:
            new_sections.append(Section(
                device_id=device.pk, slug=key[1],
                name="Recorded catalog specifications",
                sort_order=99,
            ))
            seen.add(key)
        facts_by_device[device.pk] = facts

    Section.objects.bulk_create(new_sections, ignore_conflicts=True, batch_size=300)
    ids = set(facts_by_device)
    section_ids = {
        did: sid for sid, did in Section.objects.filter(
            device_id__in=ids, slug="recorded-catalog-data"
        ).values_list("id", "device_id")
    }
    new_items = []
    for device_id, facts in facts_by_device.items():
        section_id = section_ids[device_id]
        for order, (label, value) in enumerate(facts):
            if (section_id, label) not in existing:
                new_items.append(Item(
                    section_id=section_id, label=label, value=value,
                    sort_order=order,
                ))
    Item.objects.bulk_create(new_items, ignore_conflicts=True, batch_size=500)
    print(
        f"Recorded catalog sections: {len(new_sections)} new sections, "
        f"{len(new_items)} new sourced-from-existing-field labels. "
        "No variants, prices, scores, phone identities or images changed.",
        flush=True,
    )


class Migration(migrations.Migration):
    dependencies = [("catalog", "0010_fill_xiaomi_13_pro_official_specs")]
    operations = [migrations.RunPython(populate_existing_sections, migrations.RunPython.noop)]
