"""Collect exact-model WhatMobile specifications and explicitly linked gallery photos.

This is a source-recording job, not a price scraper. It never creates variants,
copies images, or guesses back/side views. The operator confirmed WhatMobile
image reuse permission. Obey robots.txt, skip unavailable pages, rate-limit.
"""
import argparse
import csv
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from collect_whatmobile_media import candidate_paths, photo_is_accessible
from discover_retailer_phone_images import LimitedFetcher, Page, same_model

FIELDS = ("brand", "device", "product_page", "operating_system", "chipset",
          "battery_mah", "refresh_hz", "spec_sections_json", "gallery_json")
SECTIONS = {
    "build": "Build", "frequency": "Network", "processor": "Processor",
    "display": "Display", "memory": "Memory", "camera": "Camera",
    "connectivity": "Connectivity", "features": "Features", "battery": "Battery",
}
DROP_LABELS = {"price", "price in rs", "ratings", "reviews", "disclaimer"}
HOSTS = {"whatmobile.com.pk", "www.whatmobile.com.pk"}
EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def normalized(value):
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


class DetailParser(HTMLParser):
    """Parse two- or three-cell phone specification rows with row-spanning headings."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._in_row = False
        self._cell_tag = None
        self._cell_depth = 0
        self._cell_text = []
        self._cells = []
        self.links = []
        self.title = ""
        self._title = False
        self._in_h1 = 0
        self.h1 = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self._in_row = True
            self._cells = []
        elif self._in_row and tag in ("td", "th") and self._cell_tag is None:
            self._cell_tag = tag
            self._cell_depth = 0
            self._cell_text = []
        elif self._cell_tag is not None:
            self._cell_depth += 1
        if tag == "a":
            self.links.append({"url": attrs.get("href", ""),
                               "title": attrs.get("title", "")})
        if tag == "img":
            self.images.append({"url": attrs.get("data-src") or attrs.get("src") or "",
                                "alt": attrs.get("alt", "")})
        if tag == "h1":
            self._in_h1 += 1
        elif self._in_h1:
            self._in_h1 += 1
        if tag == "title":
            self._title = True

    def handle_endtag(self, tag):
        if self._cell_tag is not None:
            if tag == self._cell_tag and self._cell_depth == 0:
                text = normalized(" ".join(self._cell_text))
                self._cells.append((self._cell_tag, text))
                self._cell_tag = None
            elif self._cell_depth > 0:
                self._cell_depth -= 1
        if tag == "tr" and self._in_row:
            if self._cells:
                self.rows.append(self._cells)
            self._cells = []
            self._in_row = False
        if self._in_h1:
            self._in_h1 -= 1
        if tag == "title":
            self._title = False

    def handle_data(self, text):
        if self._cell_tag is not None:
            self._cell_text.append(text)
        if self._in_h1:
            self.h1.append(text)
        if self._title:
            self.title += text


def extract_specs(page):
    """Return only labeled spec rows inside the known WhatMobile spec sections."""
    sections = {}
    current = ""
    for cells in page.rows:
        values = [value for _, value in cells if value]
        if len(values) < 2:
            continue
        first = values[0].casefold().strip(": ")
        if first in SECTIONS and len(values) >= 3:
            current = SECTIONS[first]
            label, value = values[1], normalized(" ".join(values[2:]))
        elif first in SECTIONS and len(values) == 2:
            current = SECTIONS[first]
            continue
        elif current:
            label, value = values[0], normalized(" ".join(values[1:]))
        else:
            continue
        if (label.casefold().strip(": ") in DROP_LABELS or
                len(label) > 90 or not 1 <= len(value) <= 900 or
                len(sections.get(current, {})) >= 36):
            continue
        sections.setdefault(current, {}).setdefault(label, value)
    # Require recognized, meaningful hardware/spec sections; do not include
    # unrelated site tables before or after the detail specification table.
    if sum(len(v) for v in sections.values()) < 4:
        return {}
    return sections


def values_for(sections, section, *labels):
    fields = {k.casefold().strip(": "): v for k, v in sections.get(section, {}).items()}
    for label in labels:
        if fields.get(label):
            return fields[label]
    return ""


def scalar_specs(sections):
    os_name = values_for(sections, "Build", "os")
    ui = values_for(sections, "Build", "ui")
    if ui and os_name and len(os_name + " / " + ui) <= 80:
        os_name += " / " + ui
    if len(os_name) > 80:
        os_name = ""
    chipset = values_for(sections, "Processor", "chipset")
    if len(chipset) > 160:
        chipset = ""
    battery_text = values_for(sections, "Battery", "capacity")
    found_battery = re.search(r"\b(\d{3,5})\s*mAh\b", battery_text, flags=re.I)
    battery = int(found_battery.group(1)) if found_battery else None
    if battery is not None and not 500 <= battery <= 30000:
        battery = None
    features = values_for(sections, "Display", "extra features", "refresh rate")
    match = re.search(r"(?<!\d)(60|90|120|144|165|240)\s*Hz\b", features, flags=re.I)
    refresh = int(match.group(1)) if match else None
    return {"operating_system": os_name, "chipset": chipset,
            "battery_mah": battery or "", "refresh_hz": refresh or ""}


def gallery_urls(page, page_url, brand, device, main_image):
    """Only explicitly linked images of this model: never construct angle filenames."""
    import re
    from discover_retailer_phone_images import identity
    model_tokens = "".join(identity(f"{brand} {device}"))
    gallery = [main_image] if main_image else []
    # Links/images must have complete model identity in the filename, not just
    # a prefix: 12S must never claim 12SPro or 12SUltra photographs.
    exact_filename = re.compile(
        rf"^{re.escape(model_tokens)}(?:[-_](?:b|f|front|back|rear|side|1|2|3|4|5))?$",
        re.I,
    )
    candidates = [(row["url"], row["alt"]) for row in page.images] + [
        (row["url"], row["title"]) for row in page.links
    ]
    for raw, alt in candidates:
        url = urljoin(page_url, raw)
        parsed = urlparse(url)
        stem = Path(parsed.path).stem.casefold()
        if (parsed.scheme != "https" or parsed.hostname not in HOSTS or
                "/admin/images/" not in parsed.path.casefold() or
                Path(parsed.path).suffix.casefold() not in EXTENSIONS or
                (not exact_filename.fullmatch(stem) and
                 not (model_tokens in "".join(identity(alt)) and
                      stem in {model_tokens + "-b", model_tokens + "-f"}))):
            continue
        if url not in gallery:
            gallery.append(url)
    return gallery[:8]


def scan(catalog_path, output_path, start=0, limit=750):
    if start < 0 or not 1 <= limit <= 1000:
        raise ValueError("Invalid shard boundaries")
    with Path(catalog_path).open(newline="", encoding="utf-8-sig") as stream:
        devices = sorted({(r["brand"].strip(), r["device"].strip())
                          for r in csv.DictReader(stream)})
    fetcher = LimitedFetcher()
    rows = []
    for offset, (brand, device) in enumerate(devices[start:start+limit], 1):
        for url in candidate_paths(brand, device):
            content = fetcher.fetch(url)
            if not content:
                continue
            p = DetailParser()
            p.feed(content)
            if not same_model(normalized(" ".join(p.h1)), brand, device):
                continue
            specs = extract_specs(p)
            if not specs:
                continue
            main_page = Page()
            main_page.feed(content)
            from discover_retailer_phone_images import image_from_page
            primary = image_from_page(main_page, url, brand, device, "WhatMobile")
            photos = []
            if primary and photo_is_accessible(primary, fetcher):
                photos = [primary]
            for extra in gallery_urls(p, url, brand, device, primary):
                if extra not in photos and photo_is_accessible(extra, fetcher):
                    photos.append(extra)
            rows.append({"brand": brand, "device": device, "product_page": url,
                         **scalar_specs(specs), "spec_sections_json": json.dumps(specs, ensure_ascii=False),
                         "gallery_json": json.dumps(photos, ensure_ascii=False)})
            break
        if offset % 50 == 0:
            print(f"Details shard {start}: {offset} scanned, {len(rows)} matched", flush=True)
        time.sleep(0.25)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} exact-model WhatMobile specification records", flush=True)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=750)
    opts = parser.parse_args()
    scan(opts.catalog_csv, opts.output, opts.start, opts.limit)
