"""Verify genuine GSMArena product JPEGs for remaining blank Google phones.

Read only GSMArena's known device-specific bigpic/gallery naming conventions;
the URL is NOT accepted unless actual JPEG bytes, MIME and final CDN host all
check out. A failed probe outputs an empty research manifest and NEVER imports.
"""
import csv
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from probe_pixel_product_images import valid_jpeg_response

# Last four blank catalog identities. Pixel 5a and Pixel 5a 5G are the same
# marketed 5G model, so both share the exact 5a 5G product photo when verified.
MODELS = {
    "Pixel 5a 5G": {
        "aliases": ("Pixel 5a", "Pixel 5a 5G"),
        "gallery": "google_pixel_5a_5g-pictures-11059.php",
        "roots": (
            "google-pixel-5a-5g", "google-pixel5a-5g",
            "google-pixel-5a5g", "google-pixel5a5g",
            "google-pixel-5a", "google-pixel5a",
        ),
    },
    "Pixel 10a": {
        "aliases": ("Pixel 10a",),
        "gallery": "google_pixel_10a_5g-pictures-14474.php",
        "roots": ("google-pixel-10a-5g", "google-pixel10a-5g",
                  "google-pixel-10a", "google-pixel10a"),
    },
    "Pixel Fold": {
        "aliases": ("Pixel Fold",),
        "gallery": "google_pixel_fold-pictures-12265.php",
        "roots": ("google-pixel-fold", "google-pixelfold"),
    },
}
FIELDS = ("brand", "device", "gallery_page", "image_urls", "source_validation")
STATUS = "GSMArena exact-model CDN filename + actual JPEG data verified"


def candidates(roots):
    # Actual GSMArena product image hosts. Test only exact phone naming, not
    # arbitrary web images or other model variants.
    for root in roots:
        for num in (1, 2, 3):
            for domain in ("fdn2.gsmarena.com", "fdn.gsmarena.com"):
                yield f"https://{domain}/vv/pics/google/{root}-{num}.jpg"
        for domain in ("fdn2.gsmarena.com", "fdn.gsmarena.com"):
            yield f"https://{domain}/vv/bigpic/{root}.jpg"


def probe(catalog_path, output_path, validator=valid_jpeg_response):
    with Path(catalog_path).open(encoding="utf-8-sig", newline="") as source:
        present = {(r["brand"].casefold().strip(), r["device"].casefold().strip())
                   for r in csv.DictReader(source)}
    data = []
    for main, info in MODELS.items():
        if not any(("google", alias.casefold()) in present for alias in info["aliases"]):
            continue
        photos = []
        for url in candidates(info["roots"]):
            if validator(url):
                photos.append(url)
                if len(photos) == 3:
                    break
        if photos:
            data.append({
                "brand": "Google", "device": main,
                "gallery_page": "https://www.gsmarena.com/" + info["gallery"],
                "image_urls": json.dumps(photos),
                "source_validation": STATUS,
            })
        print(f"Google {main}: {len(photos)} validated product JPEGs", flush=True)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(data)
    print(f"Verified GSMArena galleries for {len(data)} remaining models.", flush=True)
    return data


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    probe(args.catalog, args.output)
