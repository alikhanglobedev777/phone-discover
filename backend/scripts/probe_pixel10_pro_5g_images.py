"""Try GSMArena's alternative Pixel 10 Pro 5G image naming, verify JPEG bytes.

Do not publish guesses. The verified results are a separate import because
the prior scan correctly found no images for this model.
"""
import csv
import json
from pathlib import Path

from probe_pixel_product_images import valid_jpeg_response

PAGE = "https://www.gsmarena.com/google_pixel_10_pro_5g-pictures-13987.php"
FIELDS = ("brand", "device", "gallery_page", "image_urls", "source_validation")
STEMS = (
    "google-pixel-10-pro-5g",
    "google-pixel10-pro-5g",
    "google-pixel-10-pro5g",
    "google-pixel10-pro5g",
)


def scan(catalog, output, validator=valid_jpeg_response):
    with Path(catalog).open(encoding="utf-8-sig", newline="") as f:
        models = {(r["brand"].casefold().strip(), r["device"].casefold().strip())
                  for r in csv.DictReader(f)}
    if ("google", "pixel 10 pro") not in models:
        raise RuntimeError("Pixel 10 Pro is missing from catalog")
    matched = []
    for stem in STEMS:
        for number in (1, 2, 3):
            if len(matched) >= 2:
                break
            for domain in ("fdn2.gsmarena.com", "fdn.gsmarena.com"):
                url = f"https://{domain}/vv/pics/google/{stem}-{number}.jpg"
                if validator(url):
                    matched.append(url)
                    break
        if len(matched) >= 2:
            break
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        if matched:
            writer.writerow({
                "brand": "Google", "device": "Pixel 10 Pro",
                "gallery_page": PAGE, "image_urls": json.dumps(matched),
                "source_validation": "Pixel 10 Pro 5G exact-model CDN JPEG verified",
            })
    print(f"Pixel 10 Pro: {len(matched)} verified GSMArena product JPEGs.", flush=True)
    return matched


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    scan(args.catalog, args.output)
