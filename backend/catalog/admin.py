from django.contrib import admin

from .models import (
    Brand,
    Device,
    DeviceImage,
    DeviceVariant,
    MarketOffer,
    SpecificationItem,
    SpecificationSection,
)

admin.site.site_header = "Mobile Discovery administration"
admin.site.site_title = "Mobile Discovery admin"
admin.site.index_title = "Catalog operations"


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


class DeviceVariantInline(admin.TabularInline):
    model = DeviceVariant
    extra = 0
    show_change_link = True
    fields = ("name", "ram_gb", "storage_gb", "chipset", "camera_score", "gaming_score")


class DeviceImageInline(admin.TabularInline):
    model = DeviceImage
    extra = 0
    fields = ("image_url", "alt_text", "is_primary", "sort_order")


class SpecificationSectionInline(admin.TabularInline):
    model = SpecificationSection
    extra = 0
    show_change_link = True
    fields = ("name", "slug", "sort_order")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "status", "is_published", "release_date", "last_verified_at")
    list_filter = ("is_published", "status", "brand", "operating_system")
    search_fields = ("name", "brand__name", "summary", "specification_sections__items__value")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [DeviceImageInline, DeviceVariantInline, SpecificationSectionInline]
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("brand",)
    save_on_top = True
    actions = ("publish_devices", "unpublish_devices")
    fieldsets = (
        ("Identity", {"fields": ("brand", "name", "slug", "summary")}),
        ("Launch", {"fields": ("status", "release_date", "operating_system")}),
        ("Media and source", {"fields": ("primary_image_url", "official_url")}),
        ("Legacy specification data", {"fields": ("specifications",), "classes": ("collapse",)}),
        ("Publishing", {"fields": ("is_published", "last_verified_at")}),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.action(description="Publish selected devices")
    def publish_devices(self, request, queryset):
        queryset.update(is_published=True)

    @admin.action(description="Unpublish selected devices")
    def unpublish_devices(self, request, queryset):
        queryset.update(is_published=False)


class SpecificationItemInline(admin.TabularInline):
    model = SpecificationItem
    extra = 1
    fields = ("label", "value", "sort_order")


@admin.register(SpecificationSection)
class SpecificationSectionAdmin(admin.ModelAdmin):
    list_display = ("name", "device", "sort_order")
    list_filter = ("name", "device__brand")
    search_fields = ("name", "device__name", "device__brand__name", "items__value")
    prepopulated_fields = {"slug": ("name",)}
    list_select_related = ("device", "device__brand")
    inlines = [SpecificationItemInline]


@admin.register(DeviceImage)
class DeviceImageAdmin(admin.ModelAdmin):
    list_display = ("device", "alt_text", "is_primary", "sort_order")
    list_filter = ("is_primary", "device__brand")
    search_fields = ("device__name", "device__brand__name", "alt_text")
    list_select_related = ("device", "device__brand")


@admin.register(DeviceVariant)
class DeviceVariantAdmin(admin.ModelAdmin):
    list_display = ("device", "name", "ram_gb", "storage_gb", "camera_score", "gaming_score")
    list_filter = ("ram_gb", "storage_gb")
    search_fields = ("device__name", "device__brand__name", "name", "chipset")


@admin.register(MarketOffer)
class MarketOfferAdmin(admin.ModelAdmin):
    list_display = ("variant", "country_code", "price", "currency", "seller_name", "is_available")
    list_filter = ("country_code", "currency", "is_available", "is_affiliate")
    search_fields = ("variant__device__name", "seller_name")
