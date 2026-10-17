import uuid

from rest_framework import serializers

from catalog.models import MarketPriceObservation


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


class PakistanRecommendationSerializer(serializers.Serializer):
    """Validated inputs for the DB-first Pakistani recommendation endpoint.

    Absent fields are interpreted from the user's message. Explicit filters
    take precedence. No web browsing, Gemini calls or writes to catalog data.
    """

    session_id = serializers.UUIDField(required=False, default=uuid.uuid4)
    message = serializers.CharField(max_length=1000)
    budget_pkr = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, min_value=0,
    )
    condition = serializers.ChoiceField(
        choices=MarketPriceObservation.Condition.choices,
        required=False,
    )
    grade = serializers.ChoiceField(
        choices=MarketPriceObservation.Grade.choices,
        required=False,
    )
    pta_status = serializers.ChoiceField(
        choices=MarketPriceObservation.PTAStatus.choices,
        required=False,
    )
    pta_verification = serializers.ChoiceField(
        choices=MarketPriceObservation.PTAVerification.choices,
        required=False,
    )
    city = serializers.CharField(max_length=100, required=False)
    brand = serializers.SlugField(max_length=140, required=False)
    priorities = serializers.ListField(
        child=serializers.ChoiceField(choices=PRIORITY_CHOICES),
        required=False, allow_empty=False, max_length=5,
    )
    ram_min = serializers.IntegerField(required=False, min_value=1, max_value=1024)
    storage_min = serializers.IntegerField(required=False, min_value=1, max_value=65536)
    strict_budget = serializers.BooleanField(default=True)
    max_results = serializers.IntegerField(default=3, min_value=1, max_value=5)

    def validate(self, attrs):
        if attrs.get("grade") and attrs.get("condition") not in (
            "used", "refurbished", None,
        ):
            raise serializers.ValidationError({"grade": "Grade requires used or refurbished condition."})
        if attrs.get("pta_verification") == "checked" and attrs.get("pta_status") == "unknown":
            raise serializers.ValidationError({"pta_status": "Checked PTA status cannot be unknown."})
        return attrs


class ConversationRequestSerializer(PakistanRecommendationSerializer):
    """Opt-in research and per-session structured preference memory."""

    use_memory = serializers.BooleanField(default=True)
    reset_context = serializers.BooleanField(default=False)
    research = serializers.BooleanField(default=False)
