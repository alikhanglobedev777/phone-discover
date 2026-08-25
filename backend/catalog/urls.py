from rest_framework.routers import DefaultRouter

from .views import BrandViewSet, DeviceViewSet

router = DefaultRouter()
router.register("brands", BrandViewSet, basename="brand")
router.register("devices", DeviceViewSet, basename="device")

urlpatterns = router.urls
