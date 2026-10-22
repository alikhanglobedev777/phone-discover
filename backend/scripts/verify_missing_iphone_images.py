"""Verify real GSMArena OFFICIAL iPhone product pictures for empty Apple cards.

An exact, human-reviewed model-to-gallery mapping deliberately excludes
ambiguous iPhone SE generations and prevents Pro/Plus/Max substitutions.
A candidate URL is never imported just because its filename looks plausible:
the source HTTP response must be an actual image/jpeg from GSMArena's CDN.

The operator has authorized reuse of GSMArena product images.
No product images are locally stored or changed; this is source evidence only.
"""
import argparse
import csv
import json
from pathlib import Path

from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def valid_apple_jpeg_response(url, opener=urlopen):
    """Require a real Apple GSMArena JPEG, not merely a plausible URL.

    The older Google-only validator deliberately rejects /vv/pics/apple/;
    source hosts and product folder are checked here independently.
    """
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or
            parsed.hostname != "fdn2.gsmarena.com" or
            not parsed.path.startswith("/vv/pics/apple/") or
            not parsed.path.lower().endswith(".jpg") or
            parsed.query or parsed.fragment):
        return False
    try:
        req = Request(url, headers={
            "User-Agent": "PhoneDiscoverImageCatalog/1.0 (+https://github.com/alikhanglobedev777/phone-discover)",
            "Accept": "image/jpeg",
            "Range": "bytes=0-32767",
        })
        with opener(req, timeout=12) as response:
            finished = urlsplit(response.geturl())
            if (finished.scheme != "https" or
                    finished.hostname != "fdn2.gsmarena.com" or
                    not finished.path.startswith("/vv/pics/apple/")):
                return False
            if response.headers.get("Content-Type", "").split(";")[0].strip().lower() not in (
                    "image/jpeg", "image/jpg"):
                return False
            first = response.read(32768)
            return first.startswith(b"\xff\xd8\xff") and len(first) > 4000
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return False

# Canonical full identity, GSMArena published official-pictures gallery, CDN
# filename root, and exact catalog entries. The "UW" edition is a same-model
# representative product render and may omit the US antenna window detail.
MODELS = {
    "iPhone 12": (
        "apple_iphone_12-pictures-10509.php", "apple-iphone-12",
        ("iPhone 12 UW",),
    ),
    "iPhone 14 Pro": (
        "apple_iphone_14_pro-pictures-11860.php", "apple-iphone-14-pro",
        ("iPhone 14 Pro UW",),
    ),
    "iPhone 14 Pro Max": (
        "apple_iphone_14_pro_max-pictures-11773.php", "apple-iphone-14-pro-max",
        ("iPhone 14 Pro Max UW",),
    ),
    "iPhone 15 Pro": (
        "apple_iphone_15_pro-pictures-12557.php", "apple-iphone-15-pro",
        ("iPhone 15 Pro (1TB)",),
    ),
    "iPhone 16": (
        "apple_iphone_16-pictures-13317.php", "apple-iphone-16",
        ("iPhone 16 (256GB SG)", "iPhone 16 (512GB USA)"),
    ),
    "iPhone 16 Plus": (
        "apple_iphone_16_plus-pictures-13316.php", "apple-iphone-16-plus",
        ("iPhone 16 Plus (256GB SG)", "iPhone 16 Plus (512GB USA)"),
    ),
    "iPhone 16 Pro": (
        "apple_iphone_16_pro-pictures-13315.php", "apple-iphone-16-pro",
        ("iPhone 16 Pro (1TB SG)", "iPhone 16 Pro (256GB SG)",
         "iPhone 16 Pro (512GB SG)"),
    ),
    "iPhone SE (2020)": (
        "apple_iphone_se_(2020)-pictures-10170.php", "apple-iphone-se-2020",
        ("iPhone SE 2020 2nd gen", "iPhone SE (2nd generation)"),
    ),
    "iPhone SE (2022)": (
        "apple_iphone_se_(2022)-pictures-11410.php", "apple-iphone-se-2022",
        ("iPhone SE (3rd generation)",),
    ),
}
COLUMNS = ("brand", "device", "canonical_model", "gallery_page",
           "image_urls", "source_validation")
VERIFICATION = "Exact official iPhone model + validated GSMArena CDN JPEG bytes"

def sources_for(model):
    """Try published GSMArena official-photo filename endings.

    These are only CANDIDATES; none is trusted without the real JPEG response.
    The model root is fixed in MODELS and never abbreviated.
    """
    gallery, root, targets = MODELS[model]
    for suffix in ("-1", "-2", "-0", "-3", "-00", "-01", "-4"):
        yield f"https://fdn2.gsmarena.com/vv/pics/apple/{root}{suffix}.jpg"


def verify(gap_path, output_path, checker=valid_apple_jpeg_response):
    with Path(gap_path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not {"brand", "device"}.issubset(reader.fieldnames or []):
            raise ValueError("Expected brand and device columns")
        missing = {(r["brand"].strip().casefold(), r["device"].strip().casefold())
                   for r in reader}
    validated = []
    for canonical, (page, prefix, device_names) in MODELS.items():
        to_fill = [name for name in device_names
                   if ("apple", name.casefold()) in missing]
        if not to_fill:
            continue
        images = []
        for url in sources_for(canonical):
            if checker(url):
                images.append(url)
            if len(images) == 3:
                break
        if images:
            for target in to_fill:
                validated.append({
                    "brand": "Apple", "device": target, "canonical_model": canonical,
                    "gallery_page": "https://www.gsmarena.com/" + page,
                    "image_urls": json.dumps(images),
                    "source_validation": VERIFICATION,
                })
        print(f"{canonical}: {len(images)} actual product JPEGs; "
              f"{len(to_fill)} image-less catalog editions", flush=True)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(validated)
    print(f"Verified {len(validated)} exact iPhone catalog identities of "
          f"{len([name for _, _, names in MODELS.values() for name in names if ('apple',name.casefold()) in missing])} needing images.", flush=True)
    return validated


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("image_gap_csv", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    verify(args.image_gap_csv, args.output)
