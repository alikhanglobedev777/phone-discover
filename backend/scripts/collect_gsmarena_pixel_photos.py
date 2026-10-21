"""Discover exact Google Pixel product photos published on GSMArena.

The Phone Discover operator confirmed permission to reuse GSMArena photos.
This is not a general GSMArena spider: read only the Google manufacturer index
and exact Pixel *pictures* pages for models present in our own catalog.
Respect robots.txt and standard rate limits; do not bypass anti-bot protection,
download unrelated review/news images, or guess photo URLs.
"""
import argparse
import csv
import json
import re
import time
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

INDEX_URL = "https://www.gsmarena.com/google-phones-107.php"
UA = "PhoneDiscoverPhotoResearch/1.0 (+https://github.com/alikhanglobedev777/phone-discover)"
FIELDS = ("brand", "device", "gallery_page", "image_urls", "reuse_basis")
REUSE_BASIS = "operator_confirmed_gsmarena"
DEVICE = re.compile(r"^google_(pixel_[a-z0-9_]+)-(\d{4,6})\.php$", re.I)
IMAGE_DOMAINS = {"fdn2.gsmarena.com", "fdn.gsmarena.com"}
IMAGE_SUFFIX = (".jpg", ".jpeg", ".png", ".webp")


def normalize(value):
    return "".join(re.findall(r"[a-z0-9]+", value.casefold()))


def safe_picture_url(url, device_slug):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in IMAGE_DOMAINS:
        return False
    if not parsed.path.startswith("/vv/pics/google/"):
        return False
    stem = Path(parsed.path).stem.lower()
    expected = "google-" + device_slug.replace("_", "-").lower()
    # Only exact models: Pixel 9 and Pixel 9 Pro must never share photos.
    # Official GSMArena product image filenames have an integer view suffix
    # or a simple letter, not another model/edition label.
    return bool(re.fullmatch(re.escape(expected) + r"-(?:\d{1,3}|[a-z])", stem)
                and parsed.path.lower().endswith(IMAGE_SUFFIX))


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.pictures = []
        self.title = ""
        self.h1 = ""
        self._in_title = False
        self._in_h1 = False

    def handle_starttag(self, tag, attrs):
        args = dict(attrs)
        if tag == "a" and args.get("href"):
            self.links.append(args["href"])
        if tag == "img":
            self.pictures.append((args.get("data-src") or args.get("src") or "",
                                  args.get("alt", "")))
        if tag == "title":
            self._in_title = True
        if tag == "h1":
            self._in_h1 = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "h1":
            self._in_h1 = False

    def handle_data(self, text):
        if self._in_title:
            self.title += text
        if self._in_h1:
            self.h1 += text


def exact_picture_page(page, name):
    header = page.h1.strip() or page.title.strip()
    # Require a *pictures* page with exact model name, no Pro/XL/5G conflation.
    return normalize(header.removesuffix(" pictures")) == normalize("Google " + name)


class Fetcher:
    def __init__(self):
        self.robots = {}
        self.last = 0.

    def allowed(self, url):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {"www.gsmarena.com", "gsmarena.com"}:
            return False
        base = f"https://{parsed.hostname}"
        if base not in self.robots:
            robots = RobotFileParser()
            robots.set_url(base + "/robots.txt")
            try:
                robots.read()
            except (OSError, TimeoutError):
                return False
            self.robots[base] = robots
        return self.robots[base].can_fetch(UA, url)

    def get(self, url):
        if not self.allowed(url):
            return None
        delta = time.monotonic() - self.last
        if delta < 1.5:
            time.sleep(1.5 - delta)
        self.last = time.monotonic()
        try:
            req = Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
            with urlopen(req, timeout=15) as response:
                if urlparse(response.geturl()).hostname not in {"www.gsmarena.com", "gsmarena.com"}:
                    return None
                if "text/html" not in response.headers.get("Content-Type", ""):
                    return None
                return response.read(1_000_000).decode("utf-8", "replace")
        except (OSError, ValueError, TimeoutError):
            return None


def collect(catalog_path, output_path, fetcher=None):
    with Path(catalog_path).open(encoding="utf-8-sig", newline="") as f:
        catalog = list(csv.DictReader(f))
    wanted = defaultdict(set)
    for row in catalog:
        if row["brand"].strip().casefold() == "google" and row["device"].strip().casefold().startswith("pixel"):
            wanted[normalize(row["device"].strip())].add(row["device"].strip())
    if not wanted:
        raise ValueError("No Google Pixel models exist in the curated catalog")
    fetcher = fetcher or Fetcher()
    index_html = fetcher.get(INDEX_URL)
    if index_html is None:
        raise RuntimeError("GSMArena Google index not accessible under robots/HTTP policy")
    index = Page()
    index.feed(index_html)
    candidates = defaultdict(set)
    for href in index.links:
        path = urlparse(urljoin(INDEX_URL, href)).path.lstrip("/")
        match = DEVICE.fullmatch(path)
        if not match:
            continue
        model_slug, model_id = match.groups()
        if normalize(model_slug) in wanted:
            candidates[normalize(model_slug)].add((model_slug, model_id))
    rows = []
    for key in sorted(candidates):
        # Ambiguous GSMArena IDs for one normalized name require manual review.
        if len(candidates[key]) != 1 or len(wanted[key]) != 1:
            continue
        slug, model_id = next(iter(candidates[key]))
        model_name = next(iter(wanted[key]))
        picture_page = f"https://www.gsmarena.com/google_{slug}-pictures-{model_id}.php"
        html = fetcher.get(picture_page)
        if not html:
            continue
        p = Page()
        p.feed(html)
        if not exact_picture_page(p, model_name):
            continue
        imgs = []
        for relative, alt in p.pictures:
            url = urljoin(picture_page, relative)
            if (safe_picture_url(url, slug)
                and normalize(alt) in {normalize("Google " + model_name),
                                       normalize(model_name)}
                and url not in imgs):
                imgs.append(url)
            if len(imgs) >= 6:
                break
        if imgs:
            rows.append({"brand": "Google", "device": model_name,
                         "gallery_page": picture_page,
                         "image_urls": json.dumps(imgs, ensure_ascii=False),
                         "reuse_basis": REUSE_BASIS})
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Pixel image scan: {len(wanted)} distinct catalog identities, "
          f"{len(candidates)} exact GSMArena model matches, "
          f"{len(rows)} with photo galleries. Wrote {out}", flush=True)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    opts = parser.parse_args()
    collect(opts.catalog_csv, opts.output)
