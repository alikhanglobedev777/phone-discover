from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BrandViewSet, CatalogSearchView, CatalogStatusView, DeviceViewSet

router = DefaultRouter()
router.register("brands", BrandViewSet, basename="brand")
router.register("devices", DeviceViewSet, basename="device")

urlpatterns = [
    path("status/", CatalogStatusView.as_view(), name="catalog-status"),
    path("search/", CatalogSearchView.as_view(), name="catalog-search"), *router.urls,
]
