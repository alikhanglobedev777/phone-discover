"""Read-only exact-model phone photo discovery from manufacturers' own sites.

Only public manufacturer pages with an exact product title and product-named
image are considered. Both page and image must be HTTPS on manufacturer/CDN
domains, be allowed by robots.txt, and return real image bytes. Does not
guess regional identities, use generic marketing images, bypass blocks,
or download/rehost photographs. Publisher reuse is operator-authorized.
"""
import argparse
import csv
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse, urlsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from discover_missing_brand_images import model_slug

USER_AGENT = "PhoneDiscoverOfficialMedia/1.0 (+https://github.com/alikhanglobedev777/phone-discover)"
VALIDATION = "Exact manufacturer product page + model-specific image + actual image bytes"
COLUMNS = ("brand", "device", "image_url", "publisher", "source_url", "source_validation")
SOURCES = {
    "Infinix": ("pk.infinixmobility.com", "infinixmobility.com"),
    "Tecno": ("www.tecno-mobile.com", "tecno-mobile.com"),
    "Motorola": ("www.motorola.com", "motorola.com"),
    "Vivo": ("www.vivo.com", "vivo.com"),
    "Oppo": ("www.oppo.com", "oppo.com"),
    "Xiaomi": ("www.mi.com", "mi.com"),
}
# Official brand-controlled asset domains only; don't treat a third-party
# product search or unauthenticated external CDN as a manufacturer photo.
MEDIA_DOMAINS = {
    "Infinix": ("infinixmobility.com", "transsion.com"),
    "Tecno": ("tecno-mobile.com", "transsion.com"),
    "Motorola": ("motorola.com", "motorola.com.cn"),
    "Vivo": ("vivo.com",),
    "Oppo": ("oppo.com",),
    "Xiaomi": ("mi.com", "appmifile.com"),
}


def under(host, allowed):
    return bool(host and any(host == suffix or host.endswith("." + suffix)
                             for suffix in allowed))


def tokens(s):
    # "+" is a marketed edition distinction (e.g. Note 40 Pro vs Pro+),
    # not ignorable punctuation when checking exact manufacturer identity.
    return tuple(re.findall(r"[a-z0-9]+", s.casefold().replace("+", " plus ")))


def exact_manufacturer_title(title, brand, name):
    """Require an unambiguous title segment for the whole marketed model."""
    text = re.sub(r"\s+", " ", title).strip()
    segments = re.split(r"\s+[|–—]\s+|\s+-\s+|:\s+", text)
    expected = tokens(name)
    brand_model = tokens(brand + " " + name)
    return any(tokens(segment) in (expected, brand_model)
               for segment in segments if segment.strip())


def named_model_image(candidate_name, brand, model):
    if not candidate_name:
        return False
    name_parts = tokens(candidate_name)
    model_parts = tokens(model)
    complete = tokens(brand + " " + model)
    # Exact label or label 'product photo/view/front/back'; no fuzzy prefix.
    labels = (model_parts, complete)
    suffixes = ((), ("product",), ("image",), ("photo",), ("front",),
                ("back",), ("rear",), ("render",), ("phone",), ("mobile",))
    return any(name_parts == label + suffix
               for label in labels for suffix in suffixes)


def official_pages(brand, model):
    slug = model_slug(model)
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
        # Generic family paths can resolve only for some devices. Do NOT
        # guess a product photo merely because the URL responds.
        return (
            f"https://www.motorola.com/we/en/p/phones/{slug}/",
            f"https://www.motorola.com/us/smartphones/{slug}/",
        )
    raise ValueError(brand)


class ProductPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titles = []
        self._title = False
        self._h1 = False
        self._h1_text = []
        self.og_images = []
        self.og_alt = ""
        self.images = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._title = True
        elif tag == "h1":
            self._h1 = True
            self._h1_text = []
        elif tag == "meta":
            typ = (a.get("property") or a.get("name") or "").casefold()
            if typ in ("og:image", "twitter:image") and a.get("content"):
                self.og_images.append(a["content"])
            if typ in ("og:image:alt", "twitter:image:alt"):
                self.og_alt = a.get("content", "")
        elif tag == "img":
            self.images.append((
                a.get("data-src") or a.get("data-original") or a.get("src") or "",
                a.get("alt", ""),
            ))

    def handle_endtag(self, tag):
        if tag == "title":
            self._title = False
        if tag == "h1":
            self._h1 = False
            if self._h1_text:
                self.titles.append(" ".join(self._h1_text))

    def handle_data(self, text):
        if self._title:
            self.titles.append(text)
        if self._h1:
            self._h1_text.append(text)


def image_url_approved(brand, url):
    try:
        info = urlsplit(url)
        return (info.scheme == "https" and under(info.hostname, MEDIA_DOMAINS[brand])
                and not info.username and not info.password
                and not info.query and not info.fragment
                and info.path.casefold().endswith((".jpg", ".jpeg", ".png", ".webp")))
    except ValueError:
        return False


class PoliteFetch:
    def __init__(self):
        self.robots = {}
        self.last = {}

    def allowed(self, url):
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.hostname}"
        if origin not in self.robots:
            rob = RobotFileParser()
            rob.set_url(origin + "/robots.txt")
            try:
                rob.read()
            except (HTTPError, URLError, OSError, TimeoutError):
                return False
            self.robots[origin] = rob
        return self.robots[origin].can_fetch(USER_AGENT, url)

    def get(self, url, mime):
        if not self.allowed(url):
            return None
        domain = urlsplit(url).hostname
        gap = time.monotonic() - self.last.get(domain, 0)
        if gap < 1:
            time.sleep(1 - gap)
        self.last[domain] = time.monotonic()
        try:
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "text/html" if mime == "html"
                          else "image/jpeg,image/png,image/webp",
            }
            if mime != "html":
                headers["Range"] = "bytes=0-4095"
            req = Request(url, headers=headers)
            with urlopen(req, timeout=12) as response:
                final = response.geturl()
                if (urlsplit(final).hostname != domain or
                    response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                    not in (("text/html",) if mime == "html" else
                            ("image/jpeg", "image/png", "image/webp"))):
                    return None
                data = response.read(400000 if mime == "html" else 4096)
                if mime == "html":
                    return data.decode("utf-8", "replace")
                if (data.startswith(b"\xff\xd8\xff") or
                    data.startswith(b"\x89PNG\r\n\x1a\n") or
                    (data.startswith(b"RIFF") and data[8:12] == b"WEBP")):
                    return data
        except (HTTPError, URLError, OSError, TimeoutError, ValueError):
            return None
        return None


def inspect(brand, device, fetcher):
    for product_page in official_pages(brand, device):
        if not under(urlsplit(product_page).hostname, (SOURCES[brand][1],)):
            continue
        html_text = fetcher.get(product_page, "html")
        if not html_text:
            continue
        page = ProductPage()
        page.feed(html_text)
        # A landing/category page is not an exact model page.
        if not any(exact_manufacturer_title(t, brand, device)
                   for t in page.titles):
            continue
        img_candidates = [(u, a) for u, a in page.images]
        img_candidates += [(u, page.og_alt) for u in page.og_images]
        seen = set()
        for raw, alt in img_candidates:
            url = urljoin(product_page, raw)
            if url in seen:
                continue
            seen.add(url)
            if (named_model_image(alt, brand, device) and
                image_url_approved(brand, url) and
                fetcher.get(url, "image")):
                return url, product_page
    return None


def scan(gap_csv, output_csv, brand, part=0, parts=2, fetcher=None):
    if brand not in SOURCES or not (1 <= parts <= 10 and 0 <= part < parts):
        raise ValueError("Invalid official brand/partition")
    with Path(gap_csv).open(encoding="utf-8-sig", newline="") as file:
        catalog = csv.DictReader(file)
        names = sorted({r["device"].strip() for r in catalog
                        if r["brand"].casefold().strip() == brand.casefold()
                        and r["device"].strip()}, key=str.casefold)
    selected = names[part::parts]
    fetcher = fetcher or PoliteFetch()
    rows = []
    for index, name in enumerate(selected, start=1):
        found = inspect(brand, name, fetcher)
        if found:
            url, product_page = found
            rows.append({
                "brand": brand, "device": name,
                "image_url": url, "publisher": brand,
                "source_url": product_page, "source_validation": VALIDATION,
            })
        if index % 20 == 0:
            print(f"{brand} official shard {part}: {index}/{len(selected)} scanned, "
                  f"{len(rows)} source-verified photos", flush=True)
    destination = Path(output_csv)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Manufacturer {brand} images: {len(rows)} verified of {len(selected)} sought.", flush=True)
    return rows


if __name__ == "__main__":
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument("missing_csv", type=Path)
    arg.add_argument("--brand", choices=SOURCES, required=True)
    arg.add_argument("--part", type=int, default=0)
    arg.add_argument("--parts", type=int, default=2)
    arg.add_argument("--output", type=Path, required=True)
    opts = arg.parse_args()
    scan(opts.missing_csv, opts.output, opts.brand, opts.part, opts.parts)
