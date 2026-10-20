"""Bounded factual product-page research when Google Search is unavailable."""

import re
import json
import ipaddress
import socket
from decimal import Decimal, InvalidOperation
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener

from .catalog_research import source_url
from .gemini_research import _NoRedirect
from .model_identity import matches_phone_model
from .phone_options import extract_source_options

BRANDS = {name.lower(): name for name in ("Samsung", "Xiaomi", "Redmi", "Poco", "Infinix", "Vivo", "Tecno", "Realme", "Oppo", "Apple", "Honor", "Nokia", "Google", "OnePlus", "Motorola", "Nothing", "Itel")}


class ProductPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.image = ""
        self.specs = {}
        self.text = []
        self.mode = ""
        self.label = ""
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "h1":
            self.mode, self.buffer = "title", []
        elif tag == "th" and "specs-subHeading" in attrs.get("class", ""):
            self.mode, self.buffer = "label", []
        elif tag == "td" and "specs-value" in attrs.get("class", "") and self.label:
            self.mode, self.buffer = "value", []
        elif tag == "img" and "product-image" in attrs.get("class", ""):
            self.image = attrs.get("src", "")

    def handle_data(self, data):
        if self.title:
            self.text.append(data)
        if self.mode:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if (self.mode, tag) not in (("title", "h1"), ("label", "th"), ("value", "td")):
            return
        text = " ".join(" ".join(self.buffer).split())
        if self.mode == "title":
            self.title = text
        elif self.mode == "label":
            self.label = text
        else:
            self.specs.setdefault(self.label, text)
            self.label = ""
        self.mode, self.buffer = "", []


def _fetch(url):
    if not source_url(url):
        raise ValueError("Unsupported source")
    # Any .pk merchant can be discovered. Never fetch a DNS target resolving
    # to loopback, private, link-local or reserved addresses (SSRF prevention).
    host = urlsplit(url).hostname
    try:
        resolved = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not resolved or any(not ipaddress.ip_address(addr[4][0]).is_global for addr in resolved):
            raise ValueError("Non-public source host")
    except (OSError, ValueError, TypeError, IndexError) as exc:
        raise ValueError("Could not establish a public source host") from exc
    headers = {"User-Agent": "PhoneDiscover/1.0 (product fact lookup)", "Accept": "text/html"}
    opener = build_opener(_NoRedirect())
    try:
        response = opener.open(Request(url, headers=headers), timeout=12)
    except HTTPError as exc:
        # Some Pakistani product shops require a trailing slash. Permit only
        # that exact same-origin canonical URL; never follow cross-site redirects.
        destination = urljoin(url, exc.headers.get("Location") or "")
        if (exc.code not in (301, 302, 307, 308) or destination == url
                or source_url(destination) != source_url(url)
                or urlsplit(destination).hostname != host
                or not destination.endswith("/")):
            raise
        response = opener.open(Request(destination, headers=headers), timeout=12)
    with response:
        if "text/html" not in response.headers.get("Content-Type", ""):
            raise ValueError("Not an HTML product page")
        body = response.read(1500001)
    if len(body) > 1500000:
        raise ValueError("Page too large")
    return body.decode("utf-8", errors="replace")


def parse_product(html, url, brand):
    page = ProductPage()
    page.feed(html)
    if not page.title.casefold().startswith(brand.casefold() + " "):
        raise ValueError("Product identity not found")
    text = " ".join(" ".join(page.text).split())
    # Many retailer headers contain an unrelated "Coming Soon" navigation tab.
    # Reject only a price explicitly marked as expected or coming soon.
    if re.search(r"\b(?:Rs\.?\s*Coming\s+Soon|Expected\s+Price|Price\s+Expected|Expected\s+Rs\.?)\b",
                 text[:500], re.I):
        raise ValueError("Expected pricing is not an observed retail price")
    price = re.search(r"\bRs\.?\s*([\d,]{4,})\b", text)
    memory = page.specs.get("Built-in", "")
    # WhatMobile also writes "256GB, Built-in, 12GB RAM" (comma after GB).
    # Keep the slash/list rejection below: one page price cannot price multiple SKUs.
    storage = re.search(r"(?<![\d/])\b(\d{2,4})\s*GB\s*,?\s*Built-in", memory, re.I)
    ram = re.search(r"(?<![\d/])\b(\d{1,2})\s*GB\s+RAM", memory, re.I)
    # A list of configurations cannot establish which variant owns the price.
    if not price or not ram or not storage or "/" in memory:
        raise ValueError("Unambiguous price and physical memory required")
    battery = re.search(r"(\d{3,5})\s*mAh", page.specs.get("Capacity", ""), re.I)
    refresh = re.search(r"(\d{2,3})\s*Hz", page.specs.get("Extra Features", ""), re.I)
    amount = price.group(1).replace(",", "")
    return {
        "brand": brand, "name": page.title[len(brand):].strip(), "ram_gb": int(ram.group(1)),
        "storage_gb": int(storage.group(1)), "source_url": url,
        "price_min_pkr": amount, "price_max_pkr": amount, "condition": "box_pack",
        "pta_status": "unknown", "city": "", "listing_status": "unknown",
        "image_url": urljoin(url, page.image) if page.image else "",
        "operating_system": page.specs.get("OS", "")[:80], "chipset": page.specs.get("Chipset", "")[:160],
        "battery_mah": int(battery.group(1)) if battery else None,
        "display_refresh_hz": int(refresh.group(1)) if refresh else None,
        "specifications": {key: page.specs[label][:300] for key, label in (
            ("Main camera", "Main"), ("Front camera", "Front"), ("Display", "Technology"),
            ("Screen size", "Size")) if page.specs.get(label)},
    }


def parse_priceoye_product(html, url):
    """Read explicit Product metadata; decline prices with ambiguous memory."""
    products = []
    for raw in re.findall(r'<script[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>', html, re.I | re.S):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        nodes = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        products.extend(p for p in nodes if isinstance(p, dict) and p.get("@type") == "Product")
    if len(products) != 1:
        raise ValueError("One explicit product is required")
    product = products[0]
    plain = unescape(re.sub(r"<[^>]+>", " ", html))
    variants = set(re.findall(r"\b(\d{2,4})\s*GB\s*[-–]\s*(\d{1,2})\s*GB\s*RAM\b", plain, re.I))
    if len(variants) != 1:
        raise ValueError("Price does not identify one memory configuration")
    storage, ram = next(iter(variants))
    name = product.get("name", "")
    brand = next((v for v in BRANDS.values() if name.casefold().startswith(v.casefold() + " ")), None)
    offers = product.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if len(offers) == 1 else {}
    if not brand or not isinstance(offers, dict) or offers.get("priceCurrency") != "PKR" or not offers.get("price"):
        raise ValueError("Explicit PKR product price required")
    image = product.get("image", "")
    image = image[0] if isinstance(image, list) and image else image
    return {"brand": brand, "name": name[len(brand):].strip(), "ram_gb": int(ram), "storage_gb": int(storage),
            "source_url": url, "price_min_pkr": str(offers["price"]), "price_max_pkr": str(offers["price"]),
            "condition": "box_pack", "pta_status": "unknown", "city": "", "specifications": {},
            "image_url": image if isinstance(image, str) else "",
            "listing_status": "ended" if "DISCONTINUED" in plain or str(offers.get("availability", "")).endswith("OutOfStock") else "unknown"}


def _retailer_variant(heading):
    """Only a single, explicit RAM/storage pair in the product title counts."""
    text = " ".join(unescape(re.sub(r"<[^>]*>", " ", heading)).split())
    patterns = (
        # "12GB RAM 256GB Storage" and "12GB 256GB"
        r"\b(\d{1,2})\s*GB\s*(?:RAM\s*)?[/+\- ]+\s*(\d{2,4})\s*GB\b",
        # "256GB - 12GB RAM"
        r"\b(\d{2,4})\s*GB\s*[-/+ ]+\s*(\d{1,2})\s*GB\s*RAM\b",
        # "12+256GB" / "12/256GB"
        r"\b(\d{1,2})\s*[/+]\s*(\d{2,4})\s*GB\b",
    )
    found = []
    for index, pattern in enumerate(patterns):
        for match in re.finditer(pattern, text, flags=re.I):
            a, b = (int(v) for v in match.groups())
            ram, storage = (b, a) if index == 1 else (a, b)
            if 1 <= ram <= 64 and 32 <= storage <= 4096:
                found.append((ram, storage))
    values = set(found)
    return next(iter(values)) if len(values) == 1 else None


def _pkr_amount(raw):
    try:
        price = Decimal(str(raw).replace(",", "").strip())
        if price != price.to_integral_value() or not 3000 <= price <= 20000000:
            return None
        return str(int(price))
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_pakistan_retailer_product(html, url, criteria):
    """Only an exact model + a title-specific variant + retail PKR price.

    This deliberately refuses blog estimates, multi-variant product pages,
    international currencies and ads that lack a purchaseable product listing.
    """
    target = str(criteria.get("comparison_target") or criteria.get("device_query") or "").strip()
    if not target:
        raise ValueError("Retailer import needs an exact requested model")
    heading_match = re.search(r"<h1\b[^>]*>(.*?)</h1\s*>", html, flags=re.I | re.S)
    if not heading_match:
        raise ValueError("Missing actual product title")
    heading = " ".join(unescape(re.sub(r"<[^>]+>", " ", heading_match.group(1))).split())
    variant = _retailer_variant(heading)
    if not variant:
        raise ValueError("Unambiguous memory pair is missing from product title")
    brand = next((name for name in BRANDS.values()
                  if heading.casefold().startswith(name.casefold() + " ")), None)
    if not brand:
        raise ValueError("Unrecognized phone manufacturer")
    # Product title is required to start with the exact phone identity,
    # followed by a memory variant. Extra promo words after it are not model names.
    model_in_heading = re.split(
        r"\b\d{1,4}\s*(?:GB\s*(?:RAM|ROM|Storage)?|[/+]\s*\d{2,4}\s*GB)\b",
        heading[len(brand):].strip(), maxsplit=1, flags=re.I,
    )[0].strip(" -–:|")
    if not matches_phone_model(target, brand, model_in_heading):
        raise ValueError("Retailer title does not identify requested exact model")
    # Disallow source pages without real shopping signals, e.g. price blogs.
    # JSON-LD Product+Offer is acceptable as a commerce signal too.
    plain = " ".join(unescape(re.sub(r"<[^>]+>", " ", re.sub(
        r"<(?:script|style|nav|header|footer)\b[^>]*>.*?</(?:script|style|nav|header|footer)>",
        " ", html, flags=re.I | re.S))).split())
    if not re.search(r"\b(?:add to cart|buy now|in stock|out of stock|sku|order now|checkout)\b", plain, re.I):
        raise ValueError("Not a product selling page")
    # Read a price near the specific H1, not another product in site navigation,
    # a promoted recommendation, or an unrelated price elsewhere on the page.
    price_section = html[heading_match.end():heading_match.end() + 9000]
    sale_text = " ".join(unescape(re.sub(r"<[^>]+>", " ", re.sub(
        r"<(?:script|style|nav|header|footer)\b[^>]*>.*?</(?:script|style|nav|header|footer)>",
        " ", price_section, flags=re.I | re.S))).split())
    if re.search(r"\b(?:expected price|price expected|price coming soon|coming soon \(expected)\b", sale_text[:750], re.I):
        raise ValueError("This page advertises an expected price")

    # Never substitute a crossed-out PKR list price when the actual quoted
    # selling price is in another currency.
    if re.search(r"\b(?:Special|Sale|Our|Selling)\s+Price\s*:?\s*(?:\$|USD|£|EUR)", sale_text[:1000], re.I):
        raise ValueError("Selling price is not PKR")
    amount = None
    # Prefer an actual sale/special price to crossed-out list prices.
    for pattern in (
        r"\b(?:Special|Sale|Our|Selling)\s+Price\s*:?[\s\u00a0]*(?:Rs\.?|PKR|₨)\s*([\d,]+(?:\.\d{1,2})?)",
        r"\b(?:Rs\.?|PKR|₨)\s*([\d,]+(?:\.\d{1,2})?)",
    ):
        match = re.search(pattern, sale_text[:4500], re.I)
        if match and (amount := _pkr_amount(match.group(1))):
            break
    if not amount:
        raise ValueError("No real PKR price visible on seller page")
    if criteria.get("brand") and str(criteria["brand"]).casefold() != brand.casefold():
        raise ValueError("Brand mismatch")
    return {
        "brand": brand, "name": model_in_heading, "ram_gb": variant[0], "storage_gb": variant[1],
        "source_url": url, "price_min_pkr": amount, "price_max_pkr": amount,
        "condition": "box_pack", "pta_status": "unknown", "city": "", "listing_status": "unknown",
        "image_url": "", "operating_system": "", "chipset": "", "battery_mah": None,
        "display_refresh_hz": None, "specifications": {},
    }


def _whatmobile_exact_url(criteria):
    """Build a bounded WhatMobile URL for a *specific* requested model only.

    Do not search broad brand pages for a specifications-only result: the page
    title must correspond to the exact model the visitor asked about.
    """
    brand = BRANDS.get(str(criteria.get("brand") or "").casefold())
    model = str(criteria.get("device_query") or "").strip()
    if not brand or not model:
        return None
    model = re.sub(r"\b\d{1,4}\s*(?:gb|tb)\b", " ", model, flags=re.I)
    model = re.sub(r"\b(?:pakistan|mobile|phone)\b", " ", model, flags=re.I)
    model = re.sub(r"^" + re.escape(brand) + r"\s+", "", model.strip(), flags=re.I).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 +\-]{1,63}", model):
        return None
    # "Samsung S24 Ultra" is canonically "Samsung Galaxy S24 Ultra" on
    # WhatMobile. Preserve distinctions such as Plus / Ultra / FE.
    if brand.casefold() == "samsung":
        if re.match(r"^[asfmz]\d{1,3}\b", model, re.I):
            model = "Galaxy " + model
        # WhatMobile product paths are case-sensitive.
        model = " ".join(word[:1].upper() + word[1:] for word in model.split())
    # The intent parser title-cases X90s to X90S; WhatMobile uses X90s.
    model = re.sub(r"(?<=\d)S\b", "s", model)
    return f"https://www.whatmobile.com.pk/{brand}_{'-'.join(model.split())}", brand, model


def _specifications_only_reference(criteria, *, provider):
    """Show sourced specs when an exact model lacks a verifiable retail price.

    This result MUST NOT include a price or importable phone document. Expected
    and coming-soon PKR values are not verified market offers.
    """
    target = _whatmobile_exact_url(criteria)
    if target is None:
        return None
    url, brand, model = target
    try:
        page = ProductPage()
        page.feed(_fetch(url))  # Restricted source host; redirects are blocked.
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    requested = re.sub(r"[^a-z0-9]", "", f"{brand}{model}".casefold())
    found = re.sub(r"[^a-z0-9]", "", page.title.casefold())
    if not page.title or requested != found:
        return None
    facts = []
    for label, field in (("Chipset", "Chipset"), ("Display", "Technology"),
                         ("Battery", "Capacity")):
        value = " ".join(page.specs.get(field, "").split())[:105]
        if value:
            facts.append(f"{label}: {value}")
    notice = (f"{page.title}: a specification page was found, but no verified "
              "Pakistan retail price for this exact model and variant was confirmed. "
              "Expected/coming-soon prices are not offers; no price was saved. "
              "Specifications are source-reported, not independently reviewed.")
    if facts:
        notice += " " + "; ".join(facts) + "."
    return {"status": "specifications_only", "provider": provider, "summary": "",
            "sources": [{"url": url, "title": f"{page.title} — specifications only"}],
            "results": [], "document": {"phones": []}, "notice": notice}


def research_urls(criteria, sources, *, provider):
    """Normalize searched product pages into the same source-linked phone format."""
    if criteria.get("condition") not in (None, "box_pack"):
        return {"status": "no_sources", "document": {"phones": []}, "sources": [], "notice": "These sources did not establish used-phone prices."}
    urls = list(dict.fromkeys(u for item in sources if isinstance(item, dict) and (u := source_url(item.get("url")))))[:12]
    def read(url):
        try:
            html = _fetch(url)
            host = urlsplit(url).hostname.removeprefix("www.")
            if host == "priceoye.pk":
                phone = parse_priceoye_product(html, url)
            elif host == "whatmobile.com.pk":
                brand = BRANDS.get(urlsplit(url).path.strip("/").split("_", 1)[0].lower())
                if not brand:
                    return None
                phone = parse_product(html, url, brand)
            else:
                phone = parse_pakistan_retailer_product(html, url, criteria)
            if criteria.get("brand") and phone["brand"].lower() != criteria["brand"].lower():
                return None
            # Product-page URL and parsed title must agree before we trust it.
            if urlsplit(url).hostname.removeprefix("www.") == "whatmobile.com.pk":
                path_model = urlsplit(url).path.strip("/").split("_", 1)
                if len(path_model) != 2 or not matches_phone_model(
                    path_model[1].replace("-", " "), phone["brand"], phone["name"]
                ):
                    return None
            # Search APIs return nearby products (e.g. S24+ for S24 Ultra).
            # Reject them BEFORE a nonempty result prevents direct-page fallback.
            target = criteria.get("comparison_target") or criteria.get("device_query")
            if target and not matches_phone_model(target, phone["brand"], phone["name"]):
                return None
            if criteria.get("budget_pkr") and float(phone["price_max_pkr"]) > criteria["budget_pkr"]:
                return None
            if phone["ram_gb"] < (criteria.get("ram_min") or 0) or phone["storage_gb"] < (criteria.get("storage_min") or 0):
                return None
            # These options are parsed from the actual, validated product page.
            options = extract_source_options(html, url, phone["brand"], phone["name"])
            phone["available_variants"] = options["variants"]
            phone["available_colors"] = options["colors"]
            phone["_source_parsed_options"] = True
            return phone
        except (OSError, ValueError, TypeError, AttributeError):
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        phones = [p for p in pool.map(read, urls) if p][:8]
    if not phones:
        reference = _specifications_only_reference(criteria, provider=provider)
        if reference:
            return reference
    return {"status": "grounded_preview" if phones else "no_sources", "provider": provider,
            "document": {"phones": phones},
            "sources": [{"url": p["source_url"], "title": f"{p['brand']} {p['name']}"} for p in phones],
            "notice": ("Web search found no product page with a verifiable retail PKR price and exact memory variant. "
                       "Expected or coming-soon prices are not treated as offers."
                       if not phones else
                       "Web search results were checked against product pages. Prices and specifications are source-reported; city/PTA evidence remains unconfirmed where absent.")}


def research_source_pages(criteria):
    empty = {"status": "no_sources", "summary": "", "sources": [], "results": [], "saved": {},
             "notice": "No supported source page established the requested phone/variant price."}
    if criteria.get("condition") not in (None, "box_pack"):
        return empty
    brand_key = criteria.get("brand")
    candidates = []
    target = _whatmobile_exact_url(criteria)
    if target:
        url, brand, _ = target
        candidates = [(url, brand)]
    else:
        for brand in ([BRANDS[brand_key]] if brand_key in BRANDS else ["Samsung", "Xiaomi", "Infinix"]):
            try:
                html = _fetch(f"https://www.whatmobile.com.pk/{brand}_Mobiles_Prices")
                seen = set()
                for match in re.finditer(r'href=[\"\'](' + re.escape(brand) + r'_[A-Za-z0-9-]+)[\"\']', html):
                    path = match.group(1)
                    if path in seen or path.endswith(("-Reviews", "-Pictures")):
                        continue
                    seen.add(path)
                    nearby = unescape(re.sub(r"<[^>]+>", " ", html[match.end():match.end() + 1600]))
                    price = re.search(r"Rs\.?\s*([\d,]{4,})", nearby)
                    if price and criteria.get("budget_pkr") and int(price.group(1).replace(",", "")) > criteria["budget_pkr"]:
                        continue
                    candidates.append(("https://www.whatmobile.com.pk/" + path, brand))
                    if sum(b == brand for _, b in candidates) >= 3:
                        break
            except (OSError, ValueError):
                continue
    def read(item):
        url, brand = item
        try:
            html = _fetch(url)
            phone = parse_product(html, url, brand)
            target_model = criteria.get("comparison_target") or criteria.get("device_query")
            if target_model and not matches_phone_model(target_model, phone["brand"], phone["name"]):
                return None
            if criteria.get("budget_pkr") and int(phone["price_max_pkr"]) > criteria["budget_pkr"]:
                return None
            if phone["ram_gb"] < (criteria.get("ram_min") or 0) or phone["storage_gb"] < (criteria.get("storage_min") or 0):
                return None
            # These options are parsed from the actual, validated product page.
            options = extract_source_options(html, url, phone["brand"], phone["name"])
            phone["available_variants"] = options["variants"]
            phone["available_colors"] = options["colors"]
            phone["_source_parsed_options"] = True
            return phone
        except (OSError, ValueError):
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        phones = [p for p in pool.map(read, candidates[:9]) if p][:4]
    if not phones:
        reference = _specifications_only_reference(criteria, provider="source_pages")
        return reference if reference else empty
    return {**empty, "status": "grounded_preview", "provider": "source_pages", "document": {"phones": phones},
            "sources": [{"url": p["source_url"], "title": f"{p['brand']} {p['name']} — WhatMobile"} for p in phones],
            "notice": "Researched directly from linked product pages. Prices/specifications are source-reported; city availability and PTA approval are unconfirmed."}
