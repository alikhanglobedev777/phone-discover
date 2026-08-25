import uuid

from rest_framework import serializers


PRIORITY_CHOICES = ("camera", "gaming", "battery", "display", "value")


class RecommendationRequestSerializer(serializers.Serializer):
    session_id = serializers.UUIDField(required=False, default=uuid.uuid4)
    message = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)
    budget = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=0,
    )
    currency = serializers.CharField(required=False, max_length=3)
    country_code = serializers.CharField(required=False, default="US", max_length=2)
    priorities = serializers.ListField(
        child=serializers.ChoiceField(choices=PRIORITY_CHOICES),
        required=False,
        allow_empty=True,
        max_length=5,
        default=list,
    )
    preferred_brands = serializers.ListField(
        child=serializers.CharField(max_length=120),
        required=False,
        allow_empty=True,
        max_length=5,
        default=list,
    )
    excluded_brands = serializers.ListField(
        child=serializers.CharField(max_length=120),
        required=False,
        allow_empty=True,
        max_length=5,
        default=list,
    )
    ram_min = serializers.IntegerField(required=False, default=0, min_value=0, max_value=64)
    storage_min = serializers.IntegerField(required=False, default=0, min_value=0, max_value=4096)
    strict_budget = serializers.BooleanField(required=False, default=True)
    camera_weight = serializers.FloatField(required=False, min_value=0, max_value=1)
    gaming_weight = serializers.FloatField(required=False, min_value=0, max_value=1)
    battery_weight = serializers.FloatField(required=False, min_value=0, max_value=1)
    value_weight = serializers.FloatField(required=False, min_value=0, max_value=1)

    def validate_currency(self, value):
        return value.strip().upper()

    def validate_country_code(self, value):
        return value.strip().upper()

    def validate(self, attrs):
        if not attrs.get("message", "").strip() and not any(
            (
                attrs.get("budget"),
                attrs.get("priorities"),
                attrs.get("preferred_brands"),
                attrs.get("ram_min"),
                attrs.get("storage_min"),
            )
        ):
            raise serializers.ValidationError(
                "Provide a request, budget, priority, brand, RAM, or storage requirement."
            )

        overlap = {
            brand.casefold() for brand in attrs.get("preferred_brands", [])
        } & {brand.casefold() for brand in attrs.get("excluded_brands", [])}
        if overlap:
            raise serializers.ValidationError(
                "The same brand cannot be both preferred and excluded."
            )
        return attrs
