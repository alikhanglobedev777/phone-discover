from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response

from .filters import DeviceFilter
from .models import Brand, Device
from .pricing import PRICE_GUIDE_DISCLAIMER, price_summaries_for_device
from .search import search_local_catalog
from .search_serializers import CatalogSearchQuerySerializer
from .serializers import (
    BrandSerializer, DeviceDetailSerializer, DeviceListSerializer, PakistanPriceQuerySerializer,
)


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

    @action(detail=True, methods=["get"], url_path="pakistan-prices")
    def pakistan_prices(self, request, slug=None):
        """Public, evidence-filtered price guide for one published phone."""
        device = self.get_object()
        query = PakistanPriceQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        variant_id = query.validated_data.get("variant_id")
        if variant_id is not None and not device.variants.filter(pk=variant_id).exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"variant_id": "This variant does not belong to this phone."})
        return Response({
            "device_id": device.id,
            "device_slug": device.slug,
            "currency": "PKR",
            "filters": {
                key: str(value) for key, value in query.validated_data.items()
            },
            "summaries": price_summaries_for_device(device.id, **query.validated_data),
            "disclaimer": PRICE_GUIDE_DISCLAIMER,
        })


class CatalogSearchView(APIView):
    """Strict, read-only retrieval for future Gemini tools and public filters."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "catalog_search"

    def get(self, request):
        query = CatalogSearchQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(search_local_catalog(query.validated_data))
