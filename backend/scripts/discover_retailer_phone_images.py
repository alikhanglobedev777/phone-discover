"""Research exact-model image URLs and documented colors from retail product pages.

A catalog research tool, NOT a photo license. Images on WhatMobile and
PriceOye are not assumed reusable. Output is a review manifest only;
nothing is downloaded, rehosted, or written to a production database.

Use: python backend/scripts/discover_retailer_phone_images.py \
    backend/data/phones_import_ready.csv --output backend/data/retailer_image_candidates.csv
"""
import argparse
import csv
import html
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

COLUMNS = ("brand", "device", "source", "product_page", "image_url",
           "colors", "review_status")
USER_AGENT = ("PhoneDiscoverCatalogResearch/1.0 "
              "(https://github.com/alikhanglobedev777/phone-discover; respectful image metadata audit)")
TIMEOUT = 14
HOSTS = {"whatmobile.com.pk": "WhatMobile", "priceoye.pk": "PriceOye"}


def identity(value):
    # No fuzzy matching: '12S' is not '12S Pro' or '12S Ultra'.
    return tuple(re.findall(r"[a-z0-9]+", html.unescape(value).casefold()))


def same_model(title, brand, model):
    tokens = identity(title)
    expected = identity(f"{brand} {model}")
    if tokens == expected:
        return True
    # Product titles on retail pages append a price/specification suffix.
    return len(tokens) > len(expected) and tokens[:len(expected)] == expected and (
        tokens[len(expected)] in ("price", "specifications", "specs", "in")
    )


def approved_host(url, site):
    parsed = urlparse(url)
    domain = "whatmobile.com.pk" if site == "WhatMobile" else "priceoye.pk"
    return parsed.scheme == "https" and (
        parsed.hostname == domain or
        bool(parsed.hostname and parsed.hostname.endswith("." + domain))
    )


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h1_depth = 0
        self.h1 = []
        self.page_title = ""
        self.title_depth = 0
        self.og_images = []
        self.images = []
        self._cell = False
        self._cell_text = []
        self.cells = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "h1":
            self.h1_depth += 1
        elif self.h1_depth:
            self.h1_depth += 1
        if tag == "title":
            self.title_depth += 1
        if tag in ("td", "th"):
            self._cell = True
            self._cell_text = []
        if tag == "meta" and attrs.get("property", "").lower() in ("og:image", "twitter:image"):
            self.og_images.append(attrs.get("content", ""))
        if tag == "img":
            self.images.append({
                "url": attrs.get("data-src") or attrs.get("data-original") or
                       attrs.get("src") or "",
                "alt": attrs.get("alt", ""),
                "class": attrs.get("class", ""),
            })

    def handle_endtag(self, tag):
        if self.h1_depth:
            self.h1_depth -= 1
        if tag == "title":
            self.title_depth = 0
        if tag in ("td", "th") and self._cell:
            self.cells.append(" ".join(" ".join(self._cell_text).split()))
            self._cell = False

    def handle_data(self, data):
        if self.h1_depth:
            self.h1.append(data)
        if self.title_depth:
            self.page_title += data
        if self._cell:
            self._cell_text.append(data)

    def first_color_names(self):
        for i, value in enumerate(self.cells[:-1]):
            if value.casefold().strip(" :") != "colors":
                continue
            next_value = self.cells[i + 1]
            found = [value.strip() for value in re.split(r",|[/|]", next_value)
                     if 1 < len(value.strip()) <= 50]
            if 1 <= len(found) <= 12:
                return ", ".join(found)
        return ""


def image_from_page(page, page_url, brand, model, site):
    title = " ".join(page.h1).strip() or page.page_title.strip()
    if not same_model(title, brand, model):
        return None

    expected = identity(f"{brand} {model}")
    links = []
    if site == "PriceOye":
        links.extend(page.og_images)
    for image in page.images:
        url = urljoin(page_url, image["url"])
        if site == "WhatMobile":
            # Only the actual device listing's large gallery image.
            if "/admin/images/" not in urlparse(url).path.lower():
                continue
            if " ".join(expected) not in " ".join(identity(image["alt"])):
                continue
        else:
            # PriceOye's product gallery names are generic, so prefer og:image.
            if image["alt"].casefold() not in ("slider-image", "thumbnail-image"):
                continue
        links.append(url)

    for candidate in links:
        url = urljoin(page_url, candidate)
        path = urlparse(url).path.lower()
        if approved_host(url, site) and re.search(r"\.(?:jpg|jpeg|png|webp)$", path):
            return url
    return None


def page_paths(brand, model):
    # Common canonical product paths. No site-search scraping or fuzzy results.
    brand_slug = brand.casefold()
    whatmobile = f"https://www.whatmobile.com.pk/{quote(brand.title())}_{quote(model.replace(' ', '-'))}"
    priceoye = (f"https://priceoye.pk/mobiles/{quote(brand_slug)}/"
                f"{quote(brand_slug + '-' + re.sub(r'[^a-z0-9]+', '-', model.casefold()).strip('-'))}")
    return (("WhatMobile", whatmobile), ("PriceOye", priceoye))


class LimitedFetcher:
    def __init__(self):
        self.robots = {}
        self.last_request = {}

    def can_fetch(self, url):
        base = f"{urlparse(url).scheme}://{urlparse(url).hostname}"
        if base not in self.robots:
            robot = RobotFileParser()
            robot.set_url(base + "/robots.txt")
            try:
                robot.read()
            except (OSError, HTTPError, URLError):
                # Do not crawl when robots availability is unknown.
                return False
            self.robots[base] = robot
        return self.robots[base].can_fetch(USER_AGENT, url)

    def fetch(self, url):
        if not self.can_fetch(url):
            return None
        host = urlparse(url).hostname
        gap = time.monotonic() - self.last_request.get(host, 0)
        if gap < 1.1:
            time.sleep(1.1 - gap)
        self.last_request[host] = time.monotonic()
        try:
            req = Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html",
            })
            with urlopen(req, timeout=TIMEOUT) as response:
                content_type = response.headers.get("Content-Type", "")
                if "text/html" not in content_type:
                    return None
                raw = response.read(1_200_000)
            return raw.decode("utf-8", "replace")
        except (HTTPError, URLError, TimeoutError, OSError):
            # Never bypass CAPTCHA or anti-bot checks.
            return None


def discover(input_path, output_path, start=0, limit=100):
    with Path(input_path).open(encoding="utf-8-sig", newline="") as source:
        models = sorted({(r["brand"].strip(), r["device"].strip()) for r in csv.DictReader(source)})
    if start < 0 or not 1 <= limit <= 2500:
        raise ValueError("start must be >=0 and limit 1..2500")
    fetcher = LimitedFetcher()
    photos = []
    checked = models[start:start+limit]
    for offset, (brand, model) in enumerate(checked, start + 1):
        for site, url in page_paths(brand, model):
            data = fetcher.fetch(url)
            if not data:
                continue
            page = Page()
            page.feed(data)
            image_url = image_from_page(page, url, brand, model, site)
            if not image_url:
                continue
            photos.append({
                "brand": brand, "device": model, "source": site,
                "product_page": url, "image_url": image_url,
                "colors": page.first_color_names(),
                "review_status": "REQUIRES_REUSE_RIGHTS",
            })
            break
        if offset % 50 == 0:
            print(f"Reviewed {offset}/{len(models)}; exact image candidates: {len(photos)}", flush=True)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(photos)
    print(f"Found {len(photos)} exact-model image candidates for {len(checked)} phones.")
    print("IMPORTANT: Candidate imagery is copyrighted unless separately licensed. "
          "Do not publish without permission; discovery is not an image import.")
    return photos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    discover(args.input_csv, args.output, args.start, args.limit)
