"""Promote verified GSMArena product photos on remaining Pixel identities.

Preserve prices, RAM/storage variants, all legacy media as secondary images.
Pixel 5a and Pixel 5a 5G are two catalog spellings for the same 5G product.
Manifest must have byte-verified JPEG source evidence or migration fails.
"""
import csv
import json
from pathlib import Path

from django.db import migrations


MODELS = {
    "Pixel 5a 5G": (
        "google_pixel_5a_5g-pictures-11059.php",
        ("Pixel 5a", "Pixel 5a 5G"),
        ("google-pixel-5a-5g", "google-pixel5a-5g",
         "google-pixel-5a5g", "google-pixel5a5g",
         "google-pixel-5a", "google-pixel5a"),
    ),
    "Pixel 10a": (
        "google_pixel_10a_5g-pictures-14474.php",
        ("Pixel 10a",),
        ("google-pixel-10a-5g", "google-pixel10a-5g",
         "google-pixel-10a", "google-pixel10a"),
    ),
    "Pixel Fold": (
        "google_pixel_fold-pictures-12265.php",
        ("Pixel Fold",),
        ("google-pixel-fold", "google-pixelfold"),
    ),
}
STATUS = "GSMArena exact-model CDN filename + actual JPEG data verified"


def allowed(url, roots):
    from urllib.parse import urlsplit
    p = urlsplit(url)
    if (p.scheme != "https" or p.hostname not in
        ("fdn2.gsmarena.com", "fdn.gsmarena.com")):
        return False
    exact_paths = set()
    for root in roots:
        exact_paths.add(f"/vv/bigpic/{root}.jpg")
        for n in (1, 2, 3):
            exact_paths.add(f"/vv/pics/google/{root}-{n}.jpg")
    return p.path in exact_paths and not p.query


def run(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Image = apps.get_model("catalog", "DeviceImage")
    path = Path(__file__).resolve().parents[2] / "data" / "gsmarena_remaining_pixel_photos.csv"
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise RuntimeError("GSMArena photo audit returned no actual JPEG evidence")
    seen = set()
    validated = []
    for row in rows:
        key = row["device"]
        if key not in MODELS or key in seen or row["brand"] != "Google":
            raise RuntimeError(f"Unexpected/duplicate Google media record: {key}")
        seen.add(key)
        gallery, aliases, roots = MODELS[key]
        if (row["source_validation"] != STATUS or
            row["gallery_page"] != f"https://www.gsmarena.com/{gallery}"):
            raise RuntimeError(f"Invalid GSMArena model gallery: {key}")
        photos = json.loads(row["image_urls"])
        if (not isinstance(photos, list) or not 1 <= len(photos) <= 3 or
            len(photos) != len(set(photos)) or
            any(not isinstance(u, str) or not allowed(u, roots) for u in photos)):
            raise RuntimeError(f"Invalid real product image evidence: {key}")
        validated.append((key, aliases, gallery, photos))
    images_created = 0
    phones_updated = 0
    for key, aliases, gallery, photos in validated:
        for name in aliases:
            device = Device.objects.filter(
                brand__name__iexact="Google", name__iexact=name,
                is_published=True,
            ).first()
            if not device:
                continue
            # The validated, exact-model GSMArena product image supersedes
            # illustrations but *does not delete* them.
            Image.objects.filter(device_id=device.pk, is_primary=True).update(is_primary=False)
            for index, url in enumerate(photos):
                pic, was_created = Image.objects.get_or_create(
                    device_id=device.pk, image_url=url,
                    defaults={
                        "is_primary": index == 0, "sort_order": index,
                        "alt_text": f"Google {name} GSMArena exact-model product photo"[:200],
                        "view": "unspecified",
                    },
                )
                images_created += int(was_created)
                if index == 0 and not pic.is_primary:
                    pic.is_primary = True
                    pic.sort_order = 0
                    pic.save(update_fields=["is_primary", "sort_order"])
            if device.primary_image_url != photos[0]:
                meta = dict(device.specifications or {})
                if "photo_attribution" in meta:
                    meta["secondary_image_attribution"] = meta["photo_attribution"]
                meta["photo_attribution"] = {
                    "publisher": "GSMArena", "source": f"https://www.gsmarena.com/{gallery}",
                    "reuse_basis": "permission confirmed by Phone Discover operator",
                    "verification": "actual image/jpeg response and exact model-name filename",
                }
                device.primary_image_url = photos[0]
                device.specifications = meta
                device.save(update_fields=["primary_image_url", "specifications", "updated_at"])
                phones_updated += 1
    print(f"GSMArena missing Pixel backfill: {phones_updated} primary images "
          f"and {images_created} gallery photos, existing prices and variants untouched.", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0021_add_pixel10a_fold_photos")]
    operations = [migrations.RunPython(run, migrations.RunPython.noop)]
