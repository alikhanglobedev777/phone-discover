"""Exact requested model identity; never conflate a family or brand with a phone."""

import re

from django.utils.text import slugify


def matches_phone_model(query, brand, name):
    """Compare canonical model tokens, without treating Pro/Lite/5G as optional.

    Brand prefixes and explicit RAM/storage qualifiers can be omitted in the
    user's query. An unrelated phone of the same brand must not be returned.
    """
    if not all(isinstance(value, str) for value in (query, brand, name)):
        return False
    brand_id = slugify(brand)
    if not brand_id:
        return False
    normalized_query = re.sub(r"\b\d{1,4}\s*(?:gb|tb)\b", " ", query, flags=re.I)
    normalized_query = re.sub(r"\s+(?:pakistan|mobile\s+phone|mobile)\s*$", "", normalized_query, flags=re.I)
    requested_id = slugify(normalized_query)
    model_id = slugify(name)
    prefix = brand_id + "-"
    if requested_id.startswith(prefix):
        requested_id = requested_id[len(prefix):]
    if model_id.startswith(prefix):
        model_id = model_id[len(prefix):]
    # "Samsung S24 Ultra" and "Samsung Galaxy S24 Ultra" identify the same
    # device, but S24 / S24 Plus / S24 Ultra remain different exact models.
    if brand_id == "samsung":
        stem = requested_id.removeprefix("galaxy-")
        # Treat "Samsung 26 Ultra" as Galaxy S26 Ultra, but do not turn an
        # ambiguous bare "Samsung 26" into a specific device.
        if re.fullmatch(r"\d{2}-(?:ultra|plus|fe)(?:-5g)?", stem):
            stem = "s" + stem
        # Spoken or typed "S 26 Ultra" produces a separated slug.
        stem = re.sub(r"^([asfmz])-(?=\d)", r"\1", stem)
        if re.match(r"^[asfmz]\d{1,3}(?:-|$)", stem):
            requested_id = "galaxy-" + stem
    return bool(requested_id and requested_id == model_id)
