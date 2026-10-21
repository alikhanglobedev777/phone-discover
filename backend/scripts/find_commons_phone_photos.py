"""Find independently licensed, exact-model phone photos via Wikidata P18.

Run at CI time (NOT on the web service startup). Only use exact Wikidata labels
with matching manufacturer in the smartphone description, and Wikimedia Commons
files with a compatible Creative Commons/Public Domain license. This is
conservative: unmatched phones get no photograph, never a different model.
"""
import argparse
import csv
import html
import json
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

WIKIDATA = "https://www.wikidata.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
FIELDS = ["brand", "device", "image_url", "image_page", "image_license",
          "image_license_url", "image_credit", "wikidata_id"]
ALLOWED_LICENSES = {"CC0", "CC BY 2.0", "CC BY 3.0", "CC BY 4.0",
                    "CC BY-SA 2.0", "CC BY-SA 3.0", "CC BY-SA 4.0",
                    "Public domain", "CC-PD-Mark"}
UA = "PhoneDiscover/1.0 (https://github.com/alikhanglobedev777/phone-discover; photo license audit)"


def normalized(value):
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def clean_html(value):
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()[:250]


def exact_phone_candidate(entry, brand, device):
    label = normalized(entry.get("label", ""))
    possible = {normalized(device), normalized(f"{brand} {device}")}
    if label not in possible:
        return False
    desc = normalized(entry.get("description", ""))
    manufacturer = normalized(brand)
    aliases = {
        "apple": ("apple", "iphone"),
        "google": ("google", "pixel"),
        "xiaomi": ("xiaomi", "redmi"),
        "oppo": ("oppo",),
        "vivo": ("vivo",),
        "samsung": ("samsung",),
        "motorola": ("motorola",),
        "infinix": ("infinix",),
        "tecno": ("tecno",),
        "itel": ("itel",),
    }
    company_tokens = aliases.get(manufacturer, (manufacturer,))
    return (
        any(word in desc.split() for word in ("smartphone", "phone", "mobile"))
        and any(word in desc.split() for word in company_tokens)
    )


def fetch_json(url, params):
    query = f"{url}?{urlencode(params)}"
    request = Request(query, headers={"User-Agent": UA, "Accept": "application/json"})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def commons_photo(brand, device):
    search = fetch_json(WIKIDATA, {
        "action": "wbsearchentities", "format": "json", "language": "en",
        "search": f"{brand} {device}", "limit": 8,
    })
    identities = [result for result in search.get("search", [])
                  if exact_phone_candidate(result, brand, device)]
    # Multiple distinct exact-label identities are ambiguous and require review.
    if len({item.get("id") for item in identities}) != 1:
        return None
    entity_id = identities[0]["id"]
    entity_data = fetch_json(WIKIDATA, {
        "action": "wbgetentities", "format": "json", "ids": entity_id,
        "props": "claims",
    })
    claims = entity_data.get("entities", {}).get(entity_id, {}).get("claims", {})
    image_claims = claims.get("P18", [])
    if not image_claims:
        return None
    filename = image_claims[0].get("mainsnak", {}).get("datavalue", {}).get("value")
    if not isinstance(filename, str) or not filename:
        return None
    info = fetch_json(COMMONS, {
        "action": "query", "format": "json", "titles": f"File:{filename}",
        "prop": "imageinfo", "iiprop": "url|mime|extmetadata",
    })
    pages = list(info.get("query", {}).get("pages", {}).values())
    if len(pages) != 1 or not pages[0].get("imageinfo"):
        return None
    image = pages[0]["imageinfo"][0]
    if image.get("mime") not in {"image/jpeg", "image/png", "image/webp"}:
        return None
    media_url = image.get("url", "")
    file_page = image.get("descriptionurl", "")
    if not (media_url.startswith("https://upload.wikimedia.org/")
            and file_page.startswith("https://commons.wikimedia.org/wiki/File:")):
        return None
    metadata = image.get("extmetadata", {})
    license_name = clean_html(metadata.get("LicenseShortName", {}).get("value"))
    if license_name not in ALLOWED_LICENSES:
        return None
    license_url = metadata.get("LicenseUrl", {}).get("value", "")
    if license_url and not license_url.startswith("https://"):
        return None
    credit = clean_html(metadata.get("Artist", {}).get("value")) or "Wikimedia Commons contributor"
    return {
        "brand": brand, "device": device, "image_url": media_url,
        "image_page": file_page, "image_license": license_name,
        "image_license_url": license_url, "image_credit": credit,
        "wikidata_id": entity_id,
    }


def prepare(input_csv, output_csv, start=0, limit=200):
    with Path(input_csv).open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    models = sorted({(r["brand"].strip(), r["device"].strip()) for r in rows})
    subset = models[start:start + limit]
    results = []
    failures = Counter()
    for idx, (brand, device) in enumerate(subset, start + 1):
        try:
            photo = commons_photo(brand, device)
        except (OSError, ValueError, json.JSONDecodeError):
            failures["network_error"] += 1
            photo = None
        if photo:
            results.append(photo)
        else:
            failures["no_exact_licensed_photo"] += 1
        if idx % 25 == 0:
            print(f"Checked {idx}/{len(models)} models; found {len(results)} licensed photos.", flush=True)
        time.sleep(0.2)
    out = Path(output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(results)
    print(f"Saved {len(results)} exact-model licensed images for {len(subset)} attempted models. {dict(failures)}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    if args.start < 0 or not 1 <= args.limit <= 500:
        parser.error("start must be nonnegative, limit must be 1..500")
    prepare(args.catalog_csv, args.output, args.start, args.limit)
