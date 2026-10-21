"""Validate GSMArena's actual Pixel product-image CDN URLs before importing.

The owner of Phone Discover confirmed permission to use GSMArena images.
Only accept actual JPEG bytes hosted on the GSMArena image CDN for EXACT
model-name filenames on GSMArena model-specific picture pages. This does not
crawl pages that deny automated access or create guessed database URLs.
"""
import csv
import io
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

# Canonical page IDs independently checked against GSMArena picture listings.
PAGES = {
    "Pixel 5a 5G": ("google_pixel_5a_5g-pictures-11059.php", "pixel-5a-5g"),
    "Pixel 6": ("google_pixel_6-pictures-11037.php", "pixel-6"),
    "Pixel 6a": ("google_pixel_6a-pictures-11229.php", "pixel-6a"),
    "Pixel 6 Pro": ("google_pixel_6_pro-pictures-10918.php", "pixel-6-pro"),
    "Pixel 7": ("google_pixel_7-pictures-11903.php", "pixel-7"),
    "Pixel 7a": ("google_pixel_7a-pictures-12170.php", "pixel-7a"),
    "Pixel 8": ("google_pixel_8-pictures-12546.php", "pixel-8"),
    "Pixel 8A": ("google_pixel_8a-pictures-12937.php", "pixel-8a"),
    "Pixel 9 Pro": ("google_pixel_9_pro-pictures-13218.php", "pixel-9-pro"),
    "Pixel 9 Pro Fold": ("google_pixel_9_pro_fold-pictures-13220.php", "pixel-9-pro-fold"),
    "Pixel 10 Pro": ("google_pixel_10_pro_5g-pictures-13987.php", "pixel-10-pro"),
}
FIELDS = ("brand", "device", "gallery_page", "image_urls", "source_validation")
AGENTS = {"User-Agent": "PhoneDiscover/1.0 (compatible; authorized product image audit)",
          "Accept": "image/jpeg"}

def filenames(prefix):
    # The known GSMArena catalog uses both google-pixel-X-1 and
    # google-pixelX-1 conventions. Probe: do not publish unverified guesses.
    bases = [f"google-{prefix}"]
    if prefix.startswith("pixel-"):
        bases.append("google-pixel" + prefix[len("pixel-"):])
    return [f"{base}-{number}.jpg" for base in bases for number in (1, 2)]


def valid_jpeg_response(url, opener=urlopen):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or
        parsed.hostname not in ("fdn.gsmarena.com", "fdn2.gsmarena.com") or
        not parsed.path.startswith("/vv/pics/google/") or
        not parsed.path.lower().endswith(".jpg")):
        return False
    try:
        req = Request(url, headers={**AGENTS, "Range": "bytes=0-32767"})
        with opener(req, timeout=12) as res:
            final = urlsplit(res.geturl())
            if final.hostname not in ("fdn.gsmarena.com", "fdn2.gsmarena.com"):
                return False
            if res.headers.get("Content-Type", "").split(";")[0].strip().lower() not in (
                "image/jpeg", "image/jpg"):
                return False
            head = res.read(32768)
            return head.startswith(b"\xff\xd8\xff") and len(head) > 4000
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return False


def probe(catalog_path, output_path, validator=valid_jpeg_response):
    with Path(catalog_path).open(encoding="utf-8-sig", newline="") as handle:
        catalog = {(row["brand"].casefold(), row["device"].casefold())
                   for row in csv.DictReader(handle)}
    rows = []
    for name, (page, prefix) in PAGES.items():
        if ("google", name.casefold()) not in catalog:
            continue
        matches = []
        for candidate in filenames(prefix):
            # No fabricated photos: only save a candidate if its HTTP response
            # has the expected GSMArena domain, MIME, and actual JPEG bytes.
            for domain in ("fdn2.gsmarena.com", "fdn.gsmarena.com"):
                url = f"https://{domain}/vv/pics/google/{candidate}"
                if validator(url):
                    if url not in matches:
                        matches.append(url)
                    break
            if len(matches) >= 2:
                break
            time.sleep(0.35)
        if matches:
            import json
            rows.append({
                "brand": "Google", "device": name,
                "gallery_page": "https://www.gsmarena.com/" + page,
                "image_urls": json.dumps(matches),
                "source_validation": "GSMArena exact-model filename + JPEG response verified",
            })
        print(f"{name}: {len(matches)} verified product images", flush=True)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Result: {len(rows)} GSMArena Pixel models with confirmed image bytes.", flush=True)
    return rows


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    probe(options.catalog_csv, options.output)
