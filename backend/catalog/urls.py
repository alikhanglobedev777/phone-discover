from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BrandViewSet, CatalogSearchView, DeviceViewSet

router = DefaultRouter()
router.register("brands", BrandViewSet, basename="brand")
router.register("devices", DeviceViewSet, basename="device")

urlpatterns = [path("search/", CatalogSearchView.as_view(), name="catalog-search"), *router.urls]
