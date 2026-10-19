from decimal import Decimal

from rest_framework import serializers

from .pricing import price_summaries_for_device

from .models import (
    Brand,
    Device,
    DeviceImage,
    DeviceColor,
    DeviceVariant,
    MarketOffer,
    MarketPriceObservation,
    SpecificationItem,
    SpecificationSection,
)


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name", "slug", "logo_url"]


class MarketOfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketOffer
        fields = [
            "id",
            "country_code",
            "currency",
            "price",
            "seller_name",
            "product_url",
            "is_affiliate",
            "is_available",
            "checked_at",
        ]


class DeviceColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceColor
        fields = ["id", "name", "hex_code", "sort_order"]


class DeviceImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceImage
        fields = ["id", "image_url", "alt_text", "sort_order", "is_primary", "view", "color"]


class SpecificationItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpecificationItem
        fields = ["id", "label", "value", "sort_order"]


class SpecificationSectionSerializer(serializers.ModelSerializer):
    items = SpecificationItemSerializer(many=True, read_only=True)

    class Meta:
        model = SpecificationSection
        fields = ["id", "name", "slug", "sort_order", "items"]


class DeviceVariantSerializer(serializers.ModelSerializer):
    offers = MarketOfferSerializer(many=True, read_only=True)

    class Meta:
        model = DeviceVariant
        fields = [
            "id",
            "name",
            "ram_gb",
            "storage_gb",
            "battery_mah",
            "display_refresh_hz",
            "chipset",
            "camera_score",
            "gaming_score",
            "battery_score",
            "offers",
        ]


class DeviceListSerializer(serializers.ModelSerializer):
    brand = BrandSerializer(read_only=True)
    lowest_price = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = [
            "id",
            "brand",
            "name",
            "slug",
            "summary",
            "data_source",
            "status",
            "release_date",
            "operating_system",
            "primary_image_url",
            "lowest_price",
        ]

    def get_lowest_price(self, obj):
        offer = min(
            (
                offer
                for variant in obj.variants.all()
                for offer in variant.offers.all()
                if offer.is_available
            ),
            key=lambda item: item.price,
            default=None,
        )
        if not offer:
            summaries = price_summaries_for_device(obj.id)
            if not summaries:
                return None
            best = min(summaries, key=lambda item: Decimal(item["observed_min_pkr"]))
            return {"price": best["observed_min_pkr"], "currency": "PKR", "country_code": "PK",
                    "evidence_type": best["evidence_type"]}
        return {"price": str(offer.price), "currency": offer.currency, "country_code": offer.country_code}


class PakistanPriceQuerySerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1, required=False)
    condition = serializers.ChoiceField(choices=MarketPriceObservation.Condition.choices, required=False)
    grade = serializers.ChoiceField(choices=MarketPriceObservation.Grade.choices, required=False)
    pta_status = serializers.ChoiceField(choices=MarketPriceObservation.PTAStatus.choices, required=False)
    pta_verification = serializers.ChoiceField(
        choices=MarketPriceObservation.PTAVerification.choices, required=False
    )
    city = serializers.CharField(max_length=100, allow_blank=False, trim_whitespace=True, required=False)
    budget_pkr = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False
    )

    def validate(self, attrs):
        grade = attrs.get("grade")
        condition = attrs.get("condition")
        if grade and condition not in (
            MarketPriceObservation.Condition.USED,
            MarketPriceObservation.Condition.REFURBISHED,
        ):
            raise serializers.ValidationError({"grade": "Select used or refurbished condition with a grade."})
        if (attrs.get("pta_verification") == MarketPriceObservation.PTAVerification.CHECKED
                and attrs.get("pta_status") == MarketPriceObservation.PTAStatus.UNKNOWN):
            raise serializers.ValidationError({"pta_status": "Independently checked PTA status cannot be unknown."})
        return attrs


class DeviceDetailSerializer(DeviceListSerializer):
    pakistan_prices = serializers.SerializerMethodField()

    def get_pakistan_prices(self, obj):
        return price_summaries_for_device(obj.id)

    variants = DeviceVariantSerializer(many=True, read_only=True)
    images = DeviceImageSerializer(many=True, read_only=True)
    colors = DeviceColorSerializer(many=True, read_only=True)
    specification_sections = SpecificationSectionSerializer(many=True, read_only=True)

    class Meta(DeviceListSerializer.Meta):
        fields = DeviceListSerializer.Meta.fields + [
            "official_url",
            "specifications",
            "specification_sections",
            "images",
            "colors",
            "last_verified_at",
            "variants",
            "pakistan_prices",
        ]
