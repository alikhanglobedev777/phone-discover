"""Human-operated catalog, Pakistan price, and AI research review interface."""

import json

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html

from .research_ingestion import promote_approved_price_candidate
from .admin_forms import (
    DeviceClaimAdminForm,
    IngestionCandidateReviewForm,
    MarketPriceObservationAdminForm,
    ResearchSourceAdminForm,
)
from .models import (
    Brand,
    Device,
    DeviceClaim,
    DeviceImage,
    DeviceColor,
    DeviceVariant,
    IngestionCandidate,
    MarketOffer,
    MarketPriceObservation,
    ResearchSource,
    ReviewStatus,
    SpecificationItem,
    SpecificationSection,
)

admin.site.site_header = "Phone Discover — administration"
admin.site.site_title = "Phone Discover admin"
admin.site.index_title = "Smartphone catalog & Pakistan market research"


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


class DeviceVariantInline(admin.TabularInline):
    model = DeviceVariant
    extra = 0
    show_change_link = True
    fields = (
        "name", "ram_gb", "storage_gb", "chipset", "battery_mah",
        "display_refresh_hz", "camera_score", "gaming_score", "battery_score",
    )
    verbose_name_plural = "RAM/storage variants — open a variant to add Pakistan prices"


class DeviceColorInline(admin.TabularInline):
    model = DeviceColor
    extra = 0
    fields = ("name", "hex_code", "sort_order")
    verbose_name_plural = "Official colors / finishes — save these before assigning photos"


class DeviceImageInline(admin.TabularInline):
    model = DeviceImage
    extra = 0
    fields = ("image_url", "view", "color", "alt_text", "is_primary", "sort_order")
    verbose_name_plural = "Product photography — tag front, back, side and matching finish"


class SpecificationSectionInline(admin.TabularInline):
    model = SpecificationSection
    extra = 0
    show_change_link = True
    fields = ("name", "slug", "sort_order")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        "name", "brand", "status", "variant_count", "is_published",
        "release_date", "last_verified_at",
    )
    list_filter = ("is_published", "status", "brand", "operating_system")
    search_fields = ("name", "brand__name", "summary", "specification_sections__items__value")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [DeviceColorInline, DeviceImageInline, DeviceVariantInline, SpecificationSectionInline]
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("brand",)
    save_on_top = True
    actions = ("publish_devices", "unpublish_devices")
    fieldsets = (
        ("Identity", {"fields": ("brand", "name", "slug", "summary")}),
        ("Launch and availability", {"fields": ("status", "release_date", "operating_system")}),
        ("Images and official reference", {"fields": ("primary_image_url", "official_url")}),
        (
            "Legacy machine-readable specifications",
            {"fields": ("specifications",), "classes": ("collapse",),
             "description": "For display data; detailed specifications are managed in the sections below."},
        ),
        ("Publication (manual)", {"fields": ("is_published", "last_verified_at")}),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_variant_count=Count("variants", distinct=True))

    @admin.display(description="Variants", ordering="_variant_count")
    def variant_count(self, obj):
        return obj._variant_count

    @admin.action(description="Publish selected phones (manual admin decision)", permissions=["change"])
    def publish_devices(self, request, queryset):
        count = queryset.update(is_published=True)
        self.message_user(request, f"Published {count} phone(s).", messages.SUCCESS)

    @admin.action(description="Unpublish selected phones", permissions=["change"])
    def unpublish_devices(self, request, queryset):
        count = queryset.update(is_published=False)
        self.message_user(request, f"Unpublished {count} phone(s).", messages.SUCCESS)


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


@admin.register(DeviceColor)
class DeviceColorAdmin(admin.ModelAdmin):
    list_display = ("device", "name", "hex_code", "sort_order")
    search_fields = ("device__name", "name")
    list_select_related = ("device", "device__brand")


@admin.register(DeviceImage)
class DeviceImageAdmin(admin.ModelAdmin):
    list_display = ("device", "alt_text", "view", "color", "is_primary", "sort_order")
    list_filter = ("view", "is_primary", "device__brand")
    search_fields = ("device__name", "device__brand__name", "alt_text", "color__name")
    list_select_related = ("device", "device__brand", "color")


class PakistanPriceInline(admin.StackedInline):
    model = MarketPriceObservation
    form = MarketPriceObservationAdminForm
    extra = 0
    show_change_link = True
    classes = ("collapse",)
    readonly_fields = ("reviewed_at", "created_at")
    fields = (
        ("condition", "grade", "city"),
        ("pta_status", "pta_verification", "battery_health_percent"),
        ("price_min_pkr", "price_max_pkr", "observed_at"),
        ("seller_name", "listing_url", "listing_status", "source"),
        ("verification_status", "reviewed_at", "notes"),
    )
    verbose_name_plural = "Pakistan PKR market observations (keep conditions and PTA separate)"


@admin.register(DeviceVariant)
class DeviceVariantAdmin(admin.ModelAdmin):
    list_display = (
        "device", "name", "ram_gb", "storage_gb", "chipset",
        "camera_score", "gaming_score", "battery_score", "pk_price_count",
    )
    list_filter = ("device__brand", "ram_gb", "storage_gb")
    search_fields = ("device__name", "device__brand__name", "name", "chipset")
    list_select_related = ("device", "device__brand")
    inlines = (PakistanPriceInline,)
    fieldsets = (
        ("Phone identity", {"fields": ("device", "name")}),
        ("Configuration", {"fields": ("ram_gb", "storage_gb", "chipset")}),
        ("Physical specifications", {"fields": ("battery_mah", "display_refresh_hz")}),
        (
            "Existing heuristic scores (0–100)",
            {"fields": ("camera_score", "gaming_score", "battery_score"),
             "description": "These are manual estimates, NOT validated benchmark measurements."},
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_pk_price_count=Count("pk_market_prices"))

    @admin.display(description="PKR observations", ordering="_pk_price_count")
    def pk_price_count(self, obj):
        return obj._pk_price_count


@admin.register(MarketOffer)
class MarketOfferAdmin(admin.ModelAdmin):
    list_display = ("variant", "country_code", "price", "currency", "seller_name", "is_available")
    list_filter = ("country_code", "currency", "is_available", "is_affiliate")
    search_fields = ("variant__device__name", "seller_name")
    list_select_related = ("variant", "variant__device")


@admin.register(ResearchSource)
class ResearchSourceAdmin(admin.ModelAdmin):
    form = ResearchSourceAdminForm
    list_display = ("title", "publisher", "source_type", "reuse_status", "last_checked_at")
    list_filter = ("source_type", "reuse_status")
    search_fields = ("title", "publisher", "url")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Source identity", {"fields": ("title", "url", "publisher", "source_type")}),
        (
            "Data-use assessment",
            {"fields": ("reuse_status", "reuse_notes", "last_checked_at"),
             "description": "Unknown permission is NOT permission to republish or automatically ingest data."},
        ),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


def _review_pending(model_admin, request, queryset, *, field, target, label, require_permitted=False):
    """Validate each row; never use queryset.update() for untrusted research."""
    reviewed = 0
    skipped = 0
    with transaction.atomic():
        # Lock only the review record; source may be nullable (LEFT JOIN).
        for item in queryset.select_for_update(of=("self",)).select_related("source"):
            if getattr(item, field) != ReviewStatus.PENDING:
                skipped += 1
                continue
            if require_permitted and item.source.reuse_status != ResearchSource.ReuseStatus.PERMITTED:
                skipped += 1
                continue
            setattr(item, field, target)
            item.reviewed_at = timezone.now()
            try:
                item.full_clean()
            except ValidationError:
                skipped += 1
                continue
            update_fields = [field, "reviewed_at"]
            if isinstance(item, IngestionCandidate):
                update_fields.append("updated_at")
            item.save(update_fields=update_fields)
            reviewed += 1
    if reviewed:
        model_admin.message_user(request, f"{label}: {reviewed} record(s).", messages.SUCCESS)
    if skipped:
        model_admin.message_user(
            request, f"Skipped {skipped} record(s): already reviewed or missing required evidence/permission.",
            messages.WARNING,
        )


@admin.register(MarketPriceObservation)
class MarketPriceObservationAdmin(admin.ModelAdmin):
    form = MarketPriceObservationAdminForm
    list_display = (
        "variant", "condition", "grade", "pta_status", "pta_verification", "city",
        "price_band", "verification_status", "observed_at",
    )
    list_filter = (
        "condition", "grade", "pta_status", "pta_verification", "verification_status",
        "listing_status", "city", "variant__device__brand",
    )
    search_fields = ("variant__device__name", "variant__name", "seller_name", "city")
    list_select_related = ("variant", "variant__device", "source")
    date_hierarchy = "observed_at"
    readonly_fields = ("reviewed_at", "created_at")
    actions = ("verify_selected", "reject_selected")
    save_on_top = True
    fieldsets = (
        ("Exact phone", {"fields": ("variant",)}),
        ("Pakistan condition and PTA", {"fields": (
            "condition", "grade", "pta_status", "pta_verification", "battery_health_percent", "city",
        )}),
        ("Observed PKR market price", {"fields": (
            "price_min_pkr", "price_max_pkr", "observed_at", "seller_name",
            "listing_url", "listing_status",
        )}),
        ("Verification evidence", {"fields": (
            "source", "notes", "verification_status", "reviewed_at",
        ), "description": "PTA seller claims are not proof of official handset approval. Prices are observations, not offers for sale."}),
        ("Audit", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    @admin.display(description="Observed PKR range")
    def price_band(self, obj):
        return f"PKR {obj.price_min_pkr:,.0f}–{obj.price_max_pkr:,.0f}"

    @admin.action(description="Verify selected pending price observations", permissions=["change"])
    def verify_selected(self, request, queryset):
        _review_pending(self, request, queryset, field="verification_status", target=ReviewStatus.VERIFIED, label="Verified")

    @admin.action(description="Reject selected pending price observations", permissions=["change"])
    def reject_selected(self, request, queryset):
        _review_pending(self, request, queryset, field="verification_status", target=ReviewStatus.REJECTED, label="Rejected")


@admin.register(DeviceClaim)
class DeviceClaimAdmin(admin.ModelAdmin):
    form = DeviceClaimAdminForm
    list_display = ("device", "field_path", "source", "status", "observed_at", "reviewed_at")
    list_filter = ("status", "field_path", "source__source_type")
    search_fields = ("device__name", "device__brand__name", "source__title", "field_path")
    list_select_related = ("device", "source")
    readonly_fields = ("reviewed_at", "created_at")
    actions = ("verify_selected", "reject_selected")
    fieldsets = (
        ("Evidence", {"fields": ("device", "source", "field_path", "proposed_value", "observed_at")}),
        ("Review decision", {"fields": ("status", "review_notes", "reviewed_at")}),
        ("Audit", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    @admin.action(description="Verify selected pending research claims", permissions=["change"])
    def verify_selected(self, request, queryset):
        _review_pending(
            self, request, queryset, field="status", target=ReviewStatus.VERIFIED,
            label="Verified", require_permitted=True,
        )

    @admin.action(description="Reject selected pending research claims", permissions=["change"])
    def reject_selected(self, request, queryset):
        _review_pending(self, request, queryset, field="status", target=ReviewStatus.REJECTED, label="Rejected")


@admin.register(IngestionCandidate)
class IngestionCandidateAdmin(admin.ModelAdmin):
    form = IngestionCandidateReviewForm
    list_display = ("id", "candidate_type", "source", "matched_device", "status", "created_at", "reviewed_at")
    list_filter = ("status", "candidate_type", "source__source_type")
    search_fields = ("source__title", "matched_device__name", "fingerprint")
    list_select_related = ("source", "matched_device")
    readonly_fields = (
        "candidate_type", "source", "matched_device", "payload_preview", "fingerprint",
        "created_at", "updated_at", "reviewed_at",
    )
    actions = ("approve_selected", "reject_selected", "ingest_approved_prices")
    fieldsets = (
        ("Untrusted research payload (read-only)", {"fields": (
            "candidate_type", "source", "matched_device", "fingerprint", "payload_preview",
        )}),
        (
            "Human review — approval does not ingest or publish",
            {"fields": ("status", "review_notes", "reviewed_at"),
             "description": "Only vetted sources may be approved; actual insertion requires a separate validated ingestion pipeline."},
        ),
        ("Audit", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        # Candidate records originate from the future bounded research pipeline.
        return False

    @admin.display(description="Proposed JSON — untrusted, not executed")
    def payload_preview(self, obj):
        content = json.dumps(obj.payload, indent=2, ensure_ascii=False)
        return format_html('<pre style="white-space:pre-wrap;overflow-wrap:anywhere;max-width:900px">{}</pre>', content)

    @admin.action(description="Approve selected pending candidates for later ingestion", permissions=["change"])
    def approve_selected(self, request, queryset):
        # Approval is a decision only; this action does not modify Device/DeviceVariant.
        _review_pending(
            self, request, queryset, field="status", target=IngestionCandidate.Status.APPROVED,
            label="Approved for later ingestion", require_permitted=True,
        )

    @admin.action(description="Reject selected pending candidates", permissions=["change"])
    def reject_selected(self, request, queryset):
        _review_pending(
            self, request, queryset, field="status", target=IngestionCandidate.Status.REJECTED,
            label="Rejected",
        )


    @admin.action(description="Ingest approved price leads as PENDING observations", permissions=["change"])
    def ingest_approved_prices(self, request, queryset):
        inserted = sum(1 for pk in queryset.values_list("pk", flat=True)
                       if promote_approved_price_candidate(pk))
        self.message_user(request, f"Created {inserted} pending price observation(s); independent price/PTA verification is still required.", messages.INFO)


# Keep refresh administration separate from the existing research-review workflows.
from . import price_refresh_admin  # noqa: E402,F401
