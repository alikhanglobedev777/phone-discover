from rest_framework import serializers

from .models import (
    Brand,
    Device,
    DeviceImage,
    DeviceVariant,
    MarketOffer,
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


class DeviceImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceImage
        fields = ["id", "image_url", "alt_text", "sort_order", "is_primary"]


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
            return None
        return {"price": str(offer.price), "currency": offer.currency, "country_code": offer.country_code}


class DeviceDetailSerializer(DeviceListSerializer):
    variants = DeviceVariantSerializer(many=True, read_only=True)
    images = DeviceImageSerializer(many=True, read_only=True)
    specification_sections = SpecificationSectionSerializer(many=True, read_only=True)

    class Meta(DeviceListSerializer.Meta):
        fields = DeviceListSerializer.Meta.fields + [
            "official_url",
            "specifications",
            "specification_sections",
            "images",
            "last_verified_at",
            "variants",
        ]
