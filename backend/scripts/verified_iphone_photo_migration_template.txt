"""Add real, exact-model GSMArena OFFICIAL iPhone product renders.

Every image in the bundled manifest was verified as a real JPEG on the
GSMArena image CDN by the source-checking workflow. Each name is explicitly
mapped to a published model gallery. No Pro, Max, Plus, or SE-generation mixups.

Only devices WITHOUT photos are changed. Existing gallery photographs,
device specifications, prices, memory/SIM variants and published status
remain unchanged. Source attribution labels 1TB and country/carrier
editions as representative views of the SAME model exterior.
"""
import csv
import json
from pathlib import Path
from urllib.parse import urlsplit

from django.db import migrations


MODELS = {
    "iPhone 12": ("apple_iphone_12-pictures-10509.php", "apple-iphone-12",
                  ("iPhone 12 UW",)),
    "iPhone 14 Pro": ("apple_iphone_14_pro-pictures-11860.php", "apple-iphone-14-pro",
                      ("iPhone 14 Pro UW",)),
    "iPhone 14 Pro Max": ("apple_iphone_14_pro_max-pictures-11773.php",
                          "apple-iphone-14-pro-max", ("iPhone 14 Pro Max UW",)),
    "iPhone 15 Pro": ("apple_iphone_15_pro-pictures-12557.php", "apple-iphone-15-pro",
                      ("iPhone 15 Pro (1TB)",)),
    "iPhone 16": ("apple_iphone_16-pictures-13317.php", "apple-iphone-16",
                  ("iPhone 16 (256GB SG)", "iPhone 16 (512GB USA)")),
    "iPhone 16 Plus": ("apple_iphone_16_plus-pictures-13316.php", "apple-iphone-16-plus",
                       ("iPhone 16 Plus (256GB SG)", "iPhone 16 Plus (512GB USA)")),
    "iPhone 16 Pro": ("apple_iphone_16_pro-pictures-13315.php", "apple-iphone-16-pro",
                      ("iPhone 16 Pro (1TB SG)", "iPhone 16 Pro (256GB SG)",
                       "iPhone 16 Pro (512GB SG)")),
    "iPhone SE (2020)": ("apple_iphone_se_(2020)-pictures-10170.php",
                          "apple-iphone-se-2020",
                          ("iPhone SE 2020 2nd gen", "iPhone SE (2nd generation)")),
    "iPhone SE (2022)": ("apple_iphone_se_(2022)-pictures-11410.php",
                          "apple-iphone-se-2022", ("iPhone SE (3rd generation)",)),
}
VERIFICATION = "Exact official iPhone model + validated GSMArena CDN JPEG bytes"
SUFFIXES = ("-1", "-2", "-0", "-3", "-00", "-01", "-4")


def valid_photo(url, root):
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == "fdn2.gsmarena.com"
        and not parsed.query and not parsed.fragment
        and parsed.path in {
            f"/vv/pics/apple/{root}{suffix}.jpg" for suffix in SUFFIXES
        }
    )


def import_verified_iphone_photos(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    DeviceImage = apps.get_model("catalog", "DeviceImage")
    path = Path(__file__).resolve().parents[2] / "data" / "verified_missing_iphone_images.csv"
    if not path.is_file():
        raise RuntimeError(f"Source-verified iPhone photo manifest missing: {path}")

    verified = []
    seen = set()
    claimed_photos = {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns = {"brand", "device", "canonical_model", "gallery_page",
                   "image_urls", "source_validation"}
        if not columns.issubset(reader.fieldnames or []):
            raise RuntimeError("Incomplete iPhone photo evidence columns")
        for n, row in enumerate(reader, 2):
            name = row["device"].strip()
            canonical = row["canonical_model"].strip()
            if canonical not in MODELS:
                raise RuntimeError(f"Unknown Apple model at source row {n}")
            gallery_page, root, targets = MODELS[canonical]
            if (name not in targets or name.casefold() in seen or
                row["brand"] != "Apple" or
                row["source_validation"] != VERIFICATION or
                row["gallery_page"] != f"https://www.gsmarena.com/{gallery_page}"):
                raise RuntimeError(f"Incorrect full iPhone identity or source row {n}")
            seen.add(name.casefold())
            try:
                urls = json.loads(row["image_urls"])
            except (TypeError, ValueError) as error:
                raise RuntimeError(f"Unreadable source image record {n}") from error
            if (not isinstance(urls, list) or not 1 <= len(urls) <= 3 or
                len(urls) != len(set(urls)) or
                not all(isinstance(url, str) and valid_photo(url, root)
                        for url in urls)):
                raise RuntimeError(f"Unverified iPhone JPEG on row {n}")
            for url in urls:
                if url in claimed_photos and claimed_photos[url] != canonical:
                    raise RuntimeError("GSMArena image claimed by two different iPhone models")
                claimed_photos[url] = canonical
            verified.append((name, canonical, row["gallery_page"], urls))

    if not verified:
        raise RuntimeError("No verified iPhone pictures; aborting migration")

    # Validate every input record BEFORE modifying a phone.
    existing_devices = {
        d.name.casefold(): d for d in
        Device.objects.filter(brand__name__iexact="Apple",
                              is_published=True)
    }
    occupied = set(DeviceImage.objects.values_list("device_id", flat=True))
    created = 0
    pictured = 0
    for name, canonical, page, urls in verified:
        phone = existing_devices.get(name.casefold())
        if phone is None or phone.primary_image_url or phone.pk in occupied:
            continue
        for index, url in enumerate(urls):
            DeviceImage.objects.create(
                device_id=phone.pk,
                image_url=url,
                is_primary=index == 0,
                sort_order=index,
                view="unspecified",
                alt_text=(f"Apple {name}: {canonical} official GSMArena "
                          f"product render")[:200],
            )
            created += 1
        specs = dict(phone.specifications or {})
        specs["photo_attribution"] = {
            "publisher": "GSMArena",
            "source": page,
            "reuse_basis": "permission confirmed by Phone Discover operator",
            "verification": VERIFICATION,
            "actual_model": canonical,
            "model_equivalence": "storage and market/carrier edition of same iPhone",
            "note": ("For UW/USA models, the reference render may not show "
                     "the US mmWave antenna-window detail."),
        }
        phone.primary_image_url = urls[0]
        phone.specifications = specs
        phone.save(update_fields=["primary_image_url", "specifications", "updated_at"])
        occupied.add(phone.pk)
        pictured += 1
    print(f"Official iPhone image backfill: {pictured} previously blank iPhone cards, "
          f"{created} exact-model gallery images, {len(verified)} approved source rows. "
          "No phone specifications, variants, prices or old images changed.", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0029_reuse_identical_iphone_storage_photos")]
    operations = [migrations.RunPython(
        import_verified_iphone_photos, migrations.RunPython.noop
    )]
