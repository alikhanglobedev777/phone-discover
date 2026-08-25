from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets

from .filters import DeviceFilter
from .models import Brand, Device
from .serializers import BrandSerializer, DeviceDetailSerializer, DeviceListSerializer


class BrandViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Brand.objects.filter(is_active=True)
    serializer_class = BrandSerializer
    lookup_field = "slug"


class DeviceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        Device.objects.filter(is_published=True)
        .select_related("brand")
        .prefetch_related(
            "variants__offers",
            "images",
            "specification_sections__items",
        )
    )
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = DeviceFilter
    search_fields = ["name", "brand__name", "summary", "specification_sections__items__value"]
    ordering_fields = ["name", "release_date", "status"]
    ordering = ["-release_date", "name"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return DeviceDetailSerializer
        return DeviceListSerializer
