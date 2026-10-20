"""Conservative RAM/storage and finish extraction from an *exact* product page.

No guessing of a memory cross-product, seller prices, color hex codes, or stock.
The caller must have fetched and checked the source URL separately.
"""

import json
import re
from html import unescape
from html.parser import HTMLParser

from .model_identity import matches_phone_model


MAX_VARIANTS = 16
MAX_COLORS = 16


def _plain(value):
    return " ".join(unescape(re.sub(r"<[^>]*>", " ", str(value))).split())


def _storage(value, unit):
    n = int(value) * (1024 if unit.upper() == "TB" else 1)
    return n if 32 <= n <= 4096 else None


def extract_memory_pairs(value):
    """Only explicit paired configurations; never combine two unrelated lists.

    E.g. '8GB RAM / 256GB storage' and '512GB Built-in, 12GB RAM'
    qualify. '8/12GB RAM, 128/256GB storage' does not imply four SKUs.
    """
    text = _plain(value)
    if len(text) > 800:
        return []
    patterns = (
        # 8GB RAM / 256GB Storage, 12GB 1TB, 8+128GB
        (r"\b(\d{1,2})\s*GB\s*(?:RAM\s*)?[/+\- ]+\s*(\d{2,4}|[1-4])\s*(GB|TB)\b", False),
        # 12GB RAM, 512GB Built-in (RAM-first with comma)
        (r"\b(\d{1,2})\s*GB\s*RAM\s*,\s*(\d{2,4}|[1-4])\s*(GB|TB)\s*(?:Built-in|Storage|ROM)\b", False),
        # 256GB Built-in, 8GB RAM / 1TB Storage, 16GB RAM
        (r"\b(\d{2,4}|[1-4])\s*(GB|TB)\s*(?:Built-in|Storage|ROM)\s*[,;/\- ]+\s*(\d{1,2})\s*GB\s*RAM\b", True),
        # 256GB - 12GB RAM (retailer headings)
        (r"\b(\d{2,4}|[1-4])\s*(GB|TB)\s*[-/]\s*(\d{1,2})\s*GB\s*RAM\b", True),
        # 8/128GB or 12+256GB (explicit slash notation)
        (r"\b(\d{1,2})\s*[/+]\s*(\d{2,4}|[1-4])\s*(GB|TB)\b", False),
    )
    found = []
    for pattern, storage_first in patterns:
        for match in re.finditer(pattern, text, re.I):
            if storage_first:
                amount, unit, ram_text = match.groups()
            else:
                ram_text, amount, unit = match.groups()
            ram, storage = int(ram_text), _storage(amount, unit)
            if 1 <= ram <= 64 and storage is not None and (ram, storage) not in found:
                found.append((ram, storage))
            if len(found) >= MAX_VARIANTS:
                return found
    return found


_COLOR_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 '\-+()]{1,59}$")
_COLOR_PLACEHOLDER = re.compile(r"\b(?:choose|select|option|random|assorted|varies|mixed|available|color|colour|none|default|all)\b", re.I)


def color_names(value):
    """A strictly labeled source field or product-specific select, not site text."""
    if not isinstance(value, str) or len(value) > 500:
        return []
    result = []
    for part in re.split(r"\s*(?:[,;|/]|\band\b)\s*", _plain(value), flags=re.I):
        name = part.strip(" .:-")
        if not _COLOR_NAME.fullmatch(name) or _COLOR_PLACEHOLDER.search(name):
            continue
        if name.casefold() not in {c.casefold() for c in result}:
            result.append(name)
        if len(result) >= MAX_COLORS:
            break
    return result


class _ProductSelects(HTMLParser):
    """Product-specific color select; ignore generic page/navigation options."""
    def __init__(self):
        super().__init__()
        self.active = False
        self.option = False
        self.buffer = []
        self.values = []
        self.variant_values = []
        self.kind = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select":
            label = " ".join(str(attrs.get(k, "")) for k in ("name", "id", "aria-label"))
            if re.search(r"(?:attribute|variation)[_-](?:pa[_-])?colou?r|(?:^|[^a-z])colou?r(?:$|[^a-z])", label, re.I):
                self.kind = "color"
            elif re.search(r"(?:attribute|variation)[_-](?:pa[_-])?(?:variant|configuration|memory)|(?:^|[^a-z])(?:variant|configuration|memory)(?:$|[^a-z])", label, re.I):
                self.kind = "variant"
            else:
                self.kind = ""
            self.active = bool(self.kind)
        elif tag == "option" and self.active:
            self.option, self.buffer = True, []

    def handle_data(self, value):
        if self.option:
            self.buffer.append(value)

    def handle_endtag(self, tag):
        if tag == "option" and self.option:
            (self.values if self.kind == "color" else self.variant_values).append(" ".join(self.buffer))
            self.option = False
        elif tag == "select":
            self.active = self.option = False
            self.kind = ""


def _structured_colors(html, brand, model):
    """Read JSON-LD Product.color only for a single explicitly matching product."""
    products = []
    for raw in re.findall(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S)[:8]:
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            continue
        nodes = obj if isinstance(obj, list) else obj.get("@graph", [obj]) if isinstance(obj, dict) else []
        for node in nodes:
            if not isinstance(node, dict) or node.get("@type") not in ("Product", ["Product"]):
                continue
            if matches_phone_model(str(node.get("name") or ""), brand, model):
                products.append(node)
    if len(products) != 1:
        return []
    value = products[0].get("color")
    if isinstance(value, str):
        return color_names(value)
    if isinstance(value, list) and all(isinstance(x, str) for x in value):
        return color_names(",".join(value))
    return []


def _structured_variants(html, brand, model):
    """ProductGroup.hasVariant explicit pair list; no inferred cross-product."""
    pairs = []
    for raw in re.findall(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S)[:8]:
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            continue
        nodes = obj if isinstance(obj, list) else obj.get("@graph", [obj]) if isinstance(obj, dict) else []
        for group in nodes:
            if not isinstance(group, dict) or group.get("@type") != "ProductGroup":
                continue
            if not matches_phone_model(str(group.get("name") or ""), brand, model):
                continue
            variants = group.get("hasVariant")
            if not isinstance(variants, list) or len(variants) > MAX_VARIANTS:
                continue
            for item in variants:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("name") or "")
                phone_name = re.split(r"\b\d{1,4}\s*(?:GB|TB)\b", label, maxsplit=1, flags=re.I)[0].strip(" -:|")
                if not matches_phone_model(phone_name, brand, model):
                    continue
                for pair in extract_memory_pairs(label):
                    if pair not in pairs:
                        pairs.append(pair)
                    if len(pairs) == MAX_VARIANTS:
                        return pairs
    return pairs


def extract_source_options(html, url, brand, model):
    """Return options only when this fetched page identifies the exact phone.

    WhatMobile: labeled technical specs. Other stores: product H1 and scoped
    heading/JSON-LD/color selector. No navigation-wide RAM or finish search.
    """
    from urllib.parse import urlsplit

    if not isinstance(html, str) or len(html) > 1_500_000:
        return {"variants": [], "colors": []}
    host = (urlsplit(url).hostname or "").removeprefix("www.")
    if host == "whatmobile.com.pk":
        from .source_research import ProductPage  # runtime import avoids module cycle
        product = ProductPage()
        product.feed(html)
        if not matches_phone_model(product.title, brand, model):
            return {"variants": [], "colors": []}
        memory = product.specs.get("Built-in", "")
        variants = extract_memory_pairs(memory)
        colors = color_names(product.specs.get("Colors") or product.specs.get("Color") or "")
    else:
        match = re.search(r"<h1\b[^>]*>(.*?)</h1\s*>", html, re.I | re.S)
        if not match:
            return {"variants": [], "colors": []}
        heading = _plain(match.group(1))
        # Remove explicit trailing variant *only*; model markers such as 5G, Pro,
        # Ultra, FE and Plus must still be compared exactly.
        named_model = re.split(r"\b\d{1,4}\s*(?:GB|TB)\b", heading, maxsplit=1, flags=re.I)[0].strip(" -:|")
        if not matches_phone_model(named_model, brand, model):
            return {"variants": [], "colors": []}
        variants = extract_memory_pairs(heading)
        form = _ProductSelects()
        form.feed(html[:160000])
        for label in form.variant_values:
            for pair in extract_memory_pairs(label):
                if pair not in variants:
                    variants.append(pair)
        for pair in _structured_variants(html[:160000], brand, model):
            if pair not in variants:
                variants.append(pair)
        colors = color_names(",".join(form.values))
        for color in _structured_colors(html[:160000], brand, model):
            if color.casefold() not in {c.casefold() for c in colors}:
                colors.append(color)
    return {"variants": [{"ram_gb": r, "storage_gb": s} for r, s in variants[:MAX_VARIANTS]],
            "colors": colors[:MAX_COLORS]}
