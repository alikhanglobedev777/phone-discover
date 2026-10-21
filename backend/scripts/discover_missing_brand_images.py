"""Research exact-model professional phone pictures on the permitted GSMArena CDN.

Read-only research: never changes Django or production. Uses only catalog
identities, a strict exact-model image filename and an actual JPEG response;
no lookalike phones, regional variants or made-up product photography.

Examples:
 python backend/scripts/discover_missing_brand_images.py backend/data/phones_import_ready.csv --brand Motorola --part 0 --parts 2 --output /tmp/motorola-0.csv
 python backend/scripts/discover_missing_brand_images.py backend/data/phones_import_ready.csv --brand Infinix --part 0 --parts 2 --output /tmp/infinix-0.csv
"""
import argparse
import csv
import re
import time
import unicodedata
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

HOST = "fdn2.gsmarena.com"
MEDIA_PREFIX = "/vv/pics"
BIGPIC_PREFIX = "/vv/bigpic"
# These manufacturer names are catalogue labels. The images are published by
# GSMArena, for which the Phone Discover operator separately confirmed reuse.
BRANDS = {
    "Apple": ("apple", "apple"),
    "Google": ("google", "google"),
    "Infinix": ("infinix", "infinix"),
    "Itel": ("itel", "itel"),
    "Motorola": ("motorola", "motorola"),
    "Oppo": ("oppo", "oppo"),
    "Samsung": ("samsung", "samsung"),
    "Tecno": ("tecno", "tecno"),
    "Vivo": ("vivo", "vivo"),
    "Xiaomi": ("xiaomi", "xiaomi"),
}
COLUMNS = ("brand", "device", "image_url", "publisher", "source_url",
           "source_validation")
VALIDATION = "Exact model filename; actual image/jpeg bytes verified"
UA = "PhoneDiscoverImageCatalog/1.0 (+https://github.com/alikhanglobedev777/phone-discover)"


def model_slug(name):
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = text.casefold().replace("+", " plus ").replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


def root_names(brand, name):
    slug = model_slug(name)
    if not slug:
        return []
    prefix = BRANDS[brand][0]
    # If the recorded name includes its manufacturer, don't repeat the brand.
    if slug.startswith(prefix + "-"):
        slug = slug[len(prefix) + 1:]
    roots = [f"{prefix}-{slug}"]
    # GSMArena sometimes omits hyphens before numbers within a token:
    # motorola-moto-g54, google-pixel9, etc. Never remove a model suffix.
    compact = re.sub(r"(?<=[a-z])-(?=[0-9])", "", slug)
    if compact != slug:
        roots.append(f"{prefix}-{compact}")
    return list(dict.fromkeys(roots))


def model_image_urls(brand, name):
    manufacturer, folder = BRANDS[brand]
    for root in root_names(brand, name):
        # Start with the common studio product photo filename. Never invent
        # a usable URL: every single returned candidate requires JPEG checks.
        for suffix in ("-1", "-00", "-0", "-2"):
            yield f"https://{HOST}{MEDIA_PREFIX}/{folder}/{root}{suffix}.jpg"
        yield f"https://{HOST}{BIGPIC_PREFIX}/{root}.jpg"


def valid_source_url(url, brand, model):
    """Only exact generated filenames are authorized; reject other models."""
    u = urlsplit(url)
    if u.scheme != "https" or u.hostname != HOST or u.query or u.fragment:
        return False
    return url in set(model_image_urls(brand, model))


def valid_jpeg(url, opener=urlopen):
    if urlsplit(url).hostname != HOST or urlsplit(url).scheme != "https":
        return False
    try:
        request = Request(url, headers={
            "User-Agent": UA,
            "Accept": "image/jpeg",
            "Range": "bytes=0-16383",
        })
        with opener(request, timeout=5) as response:
            final = urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname != HOST:
                return False
            if response.headers.get("Content-Type", "").split(";")[0].strip().lower() not in (
                "image/jpeg", "image/jpg"):
                return False
            data = response.read(16384)
            return len(data) >= 1024 and data.startswith(b"\xff\xd8\xff")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return False


def scan(catalog, output, brand, part=0, parts=2, checker=valid_jpeg, pace=0.15):
    if brand not in BRANDS:
        raise ValueError(f"Unrecognized brand: {brand}")
    if not 0 <= part < parts or not 1 <= parts <= 10:
        raise ValueError("Invalid partition")
    with Path(catalog).open(encoding="utf-8-sig", newline="") as stream:
        records = csv.DictReader(stream)
        identities = {}
        for row in records:
            if row["brand"].strip().casefold() == brand.casefold():
                name = row["device"].strip()
                if name:
                    identities.setdefault(name.casefold(), name)
    devices = [identities[key] for key in sorted(identities)]
    selected = devices[part::parts]
    results = []
    for i, device in enumerate(selected, 1):
        photos = []
        for candidate in model_image_urls(brand, device):
            if checker(candidate):
                photos.append(candidate)
                # Additional galleries may be collected later. First fill
                # missing primary product photos for maximum catalog coverage.
                break
            if pace:
                time.sleep(pace)
        if photos:
            results.append({
                "brand": brand, "device": device, "image_url": photos[0],
                "publisher": "GSMArena", "source_url": photos[0],
                "source_validation": VALIDATION,
            })
        if i % 40 == 0:
            print(f"{brand} shard {part}: checked {i}/{len(selected)}, found {len(results)} actual photos", flush=True)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(results)
    print(f"{brand} shard {part}: {len(results)} of {len(selected)} phones have validated product photos.", flush=True)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--brand", choices=BRANDS, required=True)
    parser.add_argument("--part", type=int, default=0)
    parser.add_argument("--parts", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    opt = parser.parse_args()
    scan(opt.catalog, opt.output, opt.brand, opt.part, opt.parts)
