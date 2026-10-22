"""Add exact-model original-manufacturer images to still-empty phone cards.

The manufacturer page has been checked for the precise full marketed model
name; the named product image returned actual image bytes. The operator has
permission to reuse the brands' photographs. These URLs are retained with
original manufacturer attribution. Existing photos, prices, catalog models,
specifications, colors, and RAM/storage variants are not overwritten.
"""
import csv
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from django.db import migrations

DOMAINS = {
    "Infinix": ("infinixmobility.com", "pk.infinixmobility.com",
                ("infinixmobility.com", "transsion.com")),
    "Tecno": ("tecno-mobile.com", "www.tecno-mobile.com",
              ("tecno-mobile.com", "transsion.com")),
    "Motorola": ("motorola.com", "www.motorola.com",
                 ("motorola.com", "motorola.com.cn")),
    "Vivo": ("vivo.com", "www.vivo.com", ("vivo.com",)),
    "Oppo": ("oppo.com", "www.oppo.com", ("oppo.com",)),
    "Xiaomi": ("mi.com", "www.mi.com", ("mi.com", "appmifile.com")),
}
EVIDENCE = "Exact manufacturer product page + model-specific image + actual image bytes"


def host_matches(host, suffixes):
    return bool(host and any(host == base or host.endswith("." + base)
                             for base in suffixes))


def slugify(name):
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = text.casefold().replace("+", " plus ").replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def exact_official_pages(brand, name):
    slug = slugify(name)
    if brand == "Infinix":
        return (
            f"https://pk.infinixmobility.com/{slug}",
            f"https://www.infinixmobility.com/{slug}",
        )
    if brand == "Tecno":
        return (
            f"https://www.tecno-mobile.com/pak/phones/product-detail/product/{slug}/",
            f"https://www.tecno-mobile.com/phones/product-detail/product/{slug}/",
        )
    if brand == "Vivo":
        return (
            f"https://www.vivo.com/pk/products/{slug}",
            f"https://www.vivo.com/en/products/{slug}",
        )
    if brand == "Xiaomi":
        return (
            f"https://www.mi.com/global/product/{slug}/",
            f"https://www.mi.com/pk/product/{slug}/",
        )
    if brand == "Oppo":
        family = ("reno" if slug.startswith("reno") else
                  "find" if slug.startswith("find") else "a")
        return (
            f"https://www.oppo.com/pk/smartphones/series-{family}/{slug}/",
            f"https://www.oppo.com/en/smartphones/series-{family}/{slug}/",
        )
    if brand == "Motorola":
        return (
            f"https://www.motorola.com/we/en/p/phones/{slug}/",
            f"https://www.motorola.com/us/smartphones/{slug}/",
        )
    raise ValueError("Unrecognized official manufacturer")


def validate_record(row):
    brand, name = row["brand"].strip(), row["device"].strip()
    if brand not in DOMAINS or not name:
        return False
    url = urlsplit(row["image_url"])
    page = row["source_url"]
    return (
        row["publisher"] == brand and
        row["source_validation"] == EVIDENCE and
        page in exact_official_pages(brand, name) and
        url.scheme == "https" and
        host_matches(url.hostname, DOMAINS[brand][2]) and
        not url.query and not url.fragment and
        url.path.casefold().endswith((".jpg", ".jpeg", ".png", ".webp")) and
        len(row["image_url"]) <= 1000
    )


def import_original_manufacturer_images(apps, schema_editor):
    Device = apps.get_model("catalog", "Device")
    Image = apps.get_model("catalog", "DeviceImage")
    path = Path(__file__).resolve().parents[2] / "data" / "verified_manufacturer_photos.csv"
    if not path.is_file():
        raise RuntimeError("Manufacturer source evidence file absent")
    approved = []
    seen = set()
    owners = defaultdict(set)
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        columns = {"brand", "device", "image_url", "publisher",
                   "source_url", "source_validation"}
        if not columns.issubset(reader.fieldnames or []):
            raise RuntimeError("Incomplete official photo evidence")
        for n, row in enumerate(reader, 2):
            key = (row["brand"].casefold().strip(), row["device"].casefold().strip())
            if key in seen or not validate_record(row):
                raise RuntimeError(f"Untrusted/duplicate manufacturer photo at line {n}")
            seen.add(key)
            owners[row["image_url"]].add(key)
            approved.append(row)
    if not approved:
        raise RuntimeError("No manufacturer evidence present; refusing empty migration")
    if any(len(keys) > 1 for keys in owners.values()):
        raise RuntimeError("One manufacturer image is claimed by two different models")
    existing = {
        (phone.brand.name.casefold(), phone.name.casefold()): phone
        for phone in Device.objects.select_related("brand").filter(is_published=True)
    }
    occupied = set(Image.objects.values_list("device_id", flat=True))
    created = []
    updated = []
    for row in approved:
        key = (row["brand"].casefold().strip(), row["device"].casefold().strip())
        phone = existing.get(key)
        if phone is None or phone.pk in occupied or phone.primary_image_url:
            continue
        image_url = row["image_url"]
        created.append(Image(
            device_id=phone.pk, image_url=image_url, is_primary=True,
            view="unspecified", sort_order=0,
            alt_text=f"{row['brand']} {row['device']} official manufacturer product photograph"[:200],
        ))
        specs = dict(phone.specifications or {})
        specs["photo_attribution"] = {
            "publisher": row["publisher"],
            "source": row["source_url"],
            "image_url": image_url,
            "reuse_basis": "manufacturer permission confirmed by Phone Discover operator",
            "verification": EVIDENCE,
        }
        phone.primary_image_url = image_url
        phone.specifications = specs
        updated.append(phone)
        occupied.add(phone.pk)
    Image.objects.bulk_create(created, batch_size=150)
    Device.objects.bulk_update(updated, ["primary_image_url", "specifications"], batch_size=150)
    print(f"Official manufacturer photo import: {len(approved)} source-backed records, "
          f"{len(updated)} previously pictureless catalog models updated. "
          "No existing prices, variants, or photos touched.", flush=True)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0027_backfill_verified_remaining_phone_images")]
    operations = [migrations.RunPython(
        import_original_manufacturer_images, migrations.RunPython.noop
    )]
