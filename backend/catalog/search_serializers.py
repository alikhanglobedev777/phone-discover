"""Strictly validated query parameters for read-only AI-ready local search."""

from rest_framework import serializers

from .models import Device, MarketPriceObservation


class CatalogSearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=120, required=False, allow_blank=False, trim_whitespace=True)
    brand = serializers.SlugField(max_length=140, required=False)
    os = serializers.CharField(max_length=80, required=False)
    status = serializers.ChoiceField(choices=Device.Status.choices, required=False)
    ram_min = serializers.IntegerField(min_value=1, max_value=1024, required=False)
    storage_min = serializers.IntegerField(min_value=1, max_value=65536, required=False)
    camera_min = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False)
    gaming_min = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False)
    battery_min = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False)
    condition = serializers.ChoiceField(choices=MarketPriceObservation.Condition.choices, required=False)
    grade = serializers.ChoiceField(choices=MarketPriceObservation.Grade.choices, required=False)
    pta_status = serializers.ChoiceField(choices=MarketPriceObservation.PTAStatus.choices, required=False)
    pta_verification = serializers.ChoiceField(choices=MarketPriceObservation.PTAVerification.choices, required=False)
    city = serializers.CharField(max_length=100, required=False, trim_whitespace=True)
    budget_pkr = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False)
    budget_mode = serializers.ChoiceField(choices=["strict", "possible"], default="strict")
    require_price = serializers.BooleanField(default=True)
    sort = serializers.ChoiceField(
        choices=["relevance", "price", "camera", "gaming", "battery", "newest", "name"],
        default="relevance",
    )
    page = serializers.IntegerField(min_value=1, max_value=10000, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=50, default=20)

    def validate(self, attrs):
        if attrs.get("grade") and attrs.get("condition") not in (
            MarketPriceObservation.Condition.USED, MarketPriceObservation.Condition.REFURBISHED,
        ):
            raise serializers.ValidationError({"grade": "Grade requires used or refurbished condition."})
        if (attrs.get("pta_verification") == MarketPriceObservation.PTAVerification.CHECKED
                and attrs.get("pta_status") == MarketPriceObservation.PTAStatus.UNKNOWN):
            raise serializers.ValidationError({"pta_status": "Checked PTA status cannot be unknown."})
        # A price constraint must not be silently ignored.
        price_only_filters = ("condition", "grade", "pta_status", "pta_verification", "city", "budget_pkr")
        if attrs.get("require_price") is False and any(k in attrs for k in price_only_filters):
            raise serializers.ValidationError({"require_price": "Price/market filters require require_price=true."})
        return attrs
