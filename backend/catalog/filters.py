import django_filters

from .models import Device


class DeviceFilter(django_filters.FilterSet):
    brand = django_filters.CharFilter(field_name="brand__slug", lookup_expr="iexact")
    os = django_filters.CharFilter(field_name="operating_system", lookup_expr="icontains")
    price_min = django_filters.NumberFilter(method="filter_price_min")
    price_max = django_filters.NumberFilter(method="filter_price_max")
    ram_min = django_filters.NumberFilter(field_name="variants__ram_gb", lookup_expr="gte")
    storage_min = django_filters.NumberFilter(field_name="variants__storage_gb", lookup_expr="gte")
    camera_score_min = django_filters.NumberFilter(
        field_name="variants__camera_score",
        lookup_expr="gte",
    )
    gaming_score_min = django_filters.NumberFilter(
        field_name="variants__gaming_score",
        lookup_expr="gte",
    )
    country = django_filters.CharFilter(method="filter_country")

    class Meta:
        model = Device
        fields = ["brand", "status", "os"]

    def filter_price_min(self, queryset, name, value):
        return queryset.filter(
            variants__offers__is_available=True,
            variants__offers__price__gte=value,
        ).distinct()

    def filter_price_max(self, queryset, name, value):
        return queryset.filter(
            variants__offers__is_available=True,
            variants__offers__price__lte=value,
        ).distinct()

    def filter_country(self, queryset, name, value):
        return queryset.filter(
            variants__offers__is_available=True,
            variants__offers__country_code=value.upper(),
        ).distinct()

    @property
    def qs(self):
        return super().qs.distinct()
