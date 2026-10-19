from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Brand(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    logo_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Device(models.Model):
    class Status(models.TextChoices):
        RUMORED = "rumored", "Rumored"
        ANNOUNCED = "announced", "Announced"
        AVAILABLE = "available", "Available"
        DISCONTINUED = "discontinued", "Discontinued"

    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="devices")
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=220, unique=True)
    summary = models.TextField(blank=True)
    release_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
        db_index=True,
    )
    operating_system = models.CharField(max_length=80, blank=True)
    primary_image_url = models.URLField(max_length=1000, blank=True)
    official_url = models.URLField(max_length=1000, blank=True)
    specifications = models.JSONField(default=dict, blank=True)
    is_published = models.BooleanField(default=False)
    data_source = models.CharField(
        max_length=20, choices=[("catalog", "Catalog"), ("web_research", "Web researched")],
        default="catalog",
    )
    last_verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-release_date", "name"]
        indexes = [
            models.Index(
                fields=["is_published", "brand"],
                name="catalog_dev_is_publ_df8385_idx",
            ),
            models.Index(fields=["name"], name="catalog_dev_name_199f08_idx"),
        ]

    def __str__(self):
        return f"{self.brand.name} {self.name}"


class DeviceColor(models.Model):
    """A documented device finish, not a promise of local availability."""

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="colors")
    name = models.CharField(max_length=80)
    hex_code = models.CharField(
        max_length=7, blank=True,
        validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Use a six-digit hex color, e.g. #8B263E.")],
        help_text="Optional representative swatch. Leave blank if the finish cannot be represented accurately.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [models.UniqueConstraint(fields=["device", "name"], name="unique_device_finish")]

    def __str__(self):
        return f"{self.device} — {self.name}"


class DeviceImage(models.Model):
    class View(models.TextChoices):
        UNSPECIFIED = "unspecified", "Product photo / angle unknown"
        FRONT = "front", "Front"
        BACK = "back", "Back"
        SIDE = "side", "Side"
        DETAIL = "detail", "Detail"

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="images")
    image_url = models.URLField(max_length=1000)
    view = models.CharField(max_length=12, choices=View.choices, default=View.UNSPECIFIED)
    color = models.ForeignKey(
        DeviceColor, on_delete=models.SET_NULL, related_name="photos", null=True, blank=True,
        help_text="Set only for a photo of this exact finish. Leave blank for generic/unidentified photos.",
    )
    alt_text = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["device", "image_url"],
                name="unique_device_image_url",
            )
        ]
        indexes = [
            models.Index(
                fields=["device", "is_primary", "sort_order"],
                name="catalog_image_device_idx",
            )
        ]

    def clean(self):
        super().clean()
        if self.color_id and self.device_id and self.color.device_id != self.device_id:
            raise ValidationError({"color": "Photo finish must belong to the same phone."})

    def __str__(self):
        return self.alt_text or f"Image for {self.device}"


class SpecificationSection(models.Model):
    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="specification_sections",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["device", "slug"],
                name="unique_device_spec_section",
            )
        ]
        indexes = [
            models.Index(
                fields=["device", "sort_order"],
                name="catalog_spec_device_order_idx",
            )
        ]

    def __str__(self):
        return f"{self.device} - {self.name}"


class SpecificationItem(models.Model):
    section = models.ForeignKey(
        SpecificationSection,
        on_delete=models.CASCADE,
        related_name="items",
    )
    label = models.CharField(max_length=120)
    value = models.TextField()
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["section", "label"],
                name="unique_section_spec_label",
            )
        ]
        indexes = [
            models.Index(
                fields=["section", "sort_order"],
                name="catalog_item_section_order_idx",
            )
        ]

    def __str__(self):
        return f"{self.section.name}: {self.label}"


class DeviceVariant(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=160)
    ram_gb = models.PositiveIntegerField(default=8)
    storage_gb = models.PositiveIntegerField(default=128)
    battery_mah = models.PositiveIntegerField(null=True, blank=True)
    display_refresh_hz = models.PositiveIntegerField(null=True, blank=True)
    chipset = models.CharField(max_length=160, blank=True)
    camera_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    gaming_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    battery_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        ordering = ["device__name", "-ram_gb", "-storage_gb"]
        constraints = [
            models.UniqueConstraint(fields=["device", "name"], name="unique_device_variant")
        ]

    def __str__(self):
        return f"{self.device} - {self.name}"


class MarketOffer(models.Model):
    variant = models.ForeignKey(DeviceVariant, on_delete=models.CASCADE, related_name="offers")
    country_code = models.CharField(max_length=2)
    currency = models.CharField(max_length=3, default="USD")
    price = models.DecimalField(max_digits=12, decimal_places=2)
    seller_name = models.CharField(max_length=160)
    product_url = models.URLField()
    is_affiliate = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    checked_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["price"]
        indexes = [
            models.Index(
                fields=["country_code", "currency", "price"],
                name="catalog_mar_country_372fb1_idx",
            ),
            models.Index(
                fields=["is_available", "country_code"],
                name="catalog_mar_is_avai_4905f8_idx",
            ),
        ]

    def __str__(self):
        return f"{self.variant} - {self.country_code} {self.price}"


# Pakistan market observations are intentionally separate from legacy MarketOffer.
# Legacy records can contain other currencies and provide no used/PTA evidence.
# The public API must not treat pending research or price observations as verified.
class ResearchSource(models.Model):
    class SourceType(models.TextChoices):
        MANUFACTURER = "manufacturer", "Manufacturer"
        RETAILER = "retailer", "Retailer"
        CLASSIFIED = "classified", "Classified listing"
        REVIEW = "review", "Independent review"
        OTHER = "other", "Other"

    class ReuseStatus(models.TextChoices):
        UNKNOWN = "unknown", "Not assessed"
        PERMITTED = "permitted", "Permitted for intended use"
        RESTRICTED = "restricted", "Restricted"

    url = models.URLField(max_length=1000, unique=True)
    title = models.CharField(max_length=255)
    publisher = models.CharField(max_length=160, blank=True)
    source_type = models.CharField(
        max_length=20, choices=SourceType.choices, default=SourceType.OTHER
    )
    reuse_status = models.CharField(
        max_length=20, choices=ReuseStatus.choices, default=ReuseStatus.UNKNOWN
    )
    reuse_notes = models.TextField(blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "id"]

    def __str__(self):
        return self.title


class ReviewStatus(models.TextChoices):
    PENDING = "pending", "Pending review"
    VERIFIED = "verified", "Verified"
    REJECTED = "rejected", "Rejected"


class DeviceClaim(models.Model):
    # field_path is descriptive evidence, NOT an arbitrary ORM attribute to write.
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="research_claims")
    source = models.ForeignKey(ResearchSource, on_delete=models.PROTECT, related_name="claims")
    field_path = models.CharField(max_length=160)
    proposed_value = models.JSONField()
    status = models.CharField(
        max_length=12, choices=ReviewStatus.choices, default=ReviewStatus.PENDING,
        db_index=True,
    )
    observed_at = models.DateTimeField(default=timezone.now)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-observed_at", "-id"]
        indexes = [
            models.Index(fields=["device", "status"], name="cat_claim_device_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(status="verified") | Q(reviewed_at__isnull=False),
                name="cat_claim_verified_reviewed",
            ),
        ]

    def clean(self):
        super().clean()
        if not self.field_path.strip():
            raise ValidationError({"field_path": "A claim must identify a field."})
        if self.status == ReviewStatus.VERIFIED and self.reviewed_at is None:
            raise ValidationError({"reviewed_at": "Verified claims need a review timestamp."})

    def __str__(self):
        return f"{self.device} · {self.field_path} ({self.status})"


class MarketPriceObservation(models.Model):
    # Used-phone PTA status belongs to a particular observed listing/unit, not a model.
    # No customer IMEI should be stored in this table.
    class Condition(models.TextChoices):
        BOX_PACK = "box_pack", "New / box pack"
        OPEN_BOX = "open_box", "Open box"
        USED = "used", "Used"
        REFURBISHED = "refurbished", "Refurbished"

    class Grade(models.TextChoices):
        EXCELLENT = "excellent", "Excellent"
        GOOD = "good", "Good"
        FAIR = "fair", "Fair"

    class PTAStatus(models.TextChoices):
        APPROVED = "approved", "PTA approved (reported or verified)"
        NON_PTA = "non_pta", "Non-PTA"
        CPID = "cpid", "CPID (not official PTA approval)"
        PATCHED = "patched", "Patched (not official PTA approval)"
        UNKNOWN = "unknown", "Unknown"

    class PTAVerification(models.TextChoices):
        UNKNOWN = "unknown", "Not checked"
        REPORTED = "reported", "Seller/source claim"
        CHECKED = "checked", "Independently checked"

    class ListingStatus(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        ACTIVE = "active", "Active when checked"
        ENDED = "ended", "Listing ended"

    variant = models.ForeignKey(
        DeviceVariant, on_delete=models.CASCADE, related_name="pk_market_prices"
    )
    source = models.ForeignKey(
        ResearchSource, on_delete=models.PROTECT, null=True, blank=True,
        related_name="price_observations",
    )
    condition = models.CharField(max_length=14, choices=Condition.choices)
    grade = models.CharField(max_length=12, choices=Grade.choices, blank=True, default="")
    pta_status = models.CharField(
        max_length=12, choices=PTAStatus.choices, default=PTAStatus.UNKNOWN
    )
    pta_verification = models.CharField(
        max_length=12, choices=PTAVerification.choices,
        default=PTAVerification.UNKNOWN,
    )
    city = models.CharField(max_length=100, blank=True)
    seller_name = models.CharField(max_length=160, blank=True)
    listing_url = models.URLField(max_length=1000, blank=True)
    listing_status = models.CharField(
        max_length=12, choices=ListingStatus.choices, default=ListingStatus.UNKNOWN
    )
    battery_health_percent = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    price_min_pkr = models.DecimalField(max_digits=12, decimal_places=2)
    price_max_pkr = models.DecimalField(max_digits=12, decimal_places=2)
    observed_at = models.DateTimeField(default=timezone.now, db_index=True)
    verification_status = models.CharField(
        max_length=12, choices=[*ReviewStatus.choices, ("web_reported", "Web research (unreviewed)")], default=ReviewStatus.PENDING,
        db_index=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-observed_at", "-id"]
        indexes = [
            models.Index(
                fields=["variant", "verification_status", "observed_at"],
                name="cat_pkprice_variant_review_idx",
            ),
            models.Index(
                fields=["condition", "pta_status", "city"],
                name="cat_pkprice_condition_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(price_min_pkr__gt=0), name="cat_pkprice_positive_min"
            ),
            models.CheckConstraint(
                condition=Q(price_max_pkr__gte=F("price_min_pkr")),
                name="cat_pkprice_ordered_range",
            ),
            models.CheckConstraint(
                condition=Q(battery_health_percent__isnull=True)
                | Q(battery_health_percent__lte=100),
                name="cat_pkprice_battery_limit",
            ),
            models.CheckConstraint(
                condition=Q(grade="") | Q(condition__in=["used", "refurbished"]),
                name="cat_pkprice_grade_condition",
            ),
            models.CheckConstraint(
                condition=~Q(pta_verification="checked") | ~Q(pta_status="unknown"),
                name="cat_pkprice_checked_pta_known",
            ),
            models.CheckConstraint(
                condition=~Q(verification_status="verified") | Q(reviewed_at__isnull=False),
                name="cat_pkprice_verified_reviewed",
            ),
            models.CheckConstraint(
                condition=~Q(verification_status="verified")
                | Q(source__isnull=False) | ~Q(notes=""),
                name="cat_pkprice_verified_evidence",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.grade and self.condition not in (self.Condition.USED, self.Condition.REFURBISHED):
            errors["grade"] = "Only used/refurbished phones can have a condition grade."
        if (self.pta_verification == self.PTAVerification.CHECKED
                and self.pta_status == self.PTAStatus.UNKNOWN):
            errors["pta_verification"] = "PTA status cannot be unknown if independently checked."
        if self.verification_status == ReviewStatus.VERIFIED:
            if self.reviewed_at is None:
                errors["reviewed_at"] = "Verified prices need a review timestamp."
            if self.source_id is None and not self.notes.strip():
                errors["source"] = "Verified prices require a source or documented admin evidence."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (f"{self.variant} · {self.condition} · {self.pta_status} "
                f"· PKR {self.price_min_pkr}–{self.price_max_pkr}")


class IngestionCandidate(models.Model):
    class CandidateType(models.TextChoices):
        DEVICE = "device", "Phone identity"
        SPECIFICATIONS = "specifications", "Phone specifications"
        PRICE = "price", "Market price"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved for ingestion"
        REJECTED = "rejected", "Rejected"
        INGESTED = "ingested", "Ingested"

    candidate_type = models.CharField(max_length=20, choices=CandidateType.choices)
    source = models.ForeignKey(
        ResearchSource, on_delete=models.PROTECT, related_name="ingestion_candidates"
    )
    matched_device = models.ForeignKey(
        Device, on_delete=models.SET_NULL, related_name="ingestion_candidates",
        null=True, blank=True,
    )
    # Store only structured candidate facts, not executable instructions.
    payload = models.JSONField(default=dict)
    fingerprint = models.CharField(max_length=64, null=True, blank=True, unique=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    review_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "candidate_type"], name="cat_ingest_status_type_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status="pending") | Q(reviewed_at__isnull=False),
                name="cat_ingest_reviewed_time",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if not isinstance(self.payload, dict):
            errors["payload"] = "Candidate payload must be a JSON object."
        if self.status != self.Status.PENDING and self.reviewed_at is None:
            errors["reviewed_at"] = "Reviewed candidates require a review timestamp."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.candidate_type} research candidate #{self.pk} ({self.status})"


from django.conf import settings  # imported here to avoid touching existing catalog/model imports


class PriceRefreshRun(models.Model):
    """Operator-visible audit trail; remote source contents are never stored here."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class Origin(models.TextChoices):
        ADMIN = "admin", "Admin button"
        SCHEDULED = "scheduled", "48-hour scheduler"
        CLI = "cli", "Command line"

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED, db_index=True)
    origin = models.CharField(max_length=12, choices=Origin.choices, default=Origin.CLI)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="price_refresh_runs"
    )
    force = models.BooleanField(default=False)
    counts = models.JSONField(default=dict, blank=True)
    notice = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"Price refresh #{self.pk} ({self.status})"


class PriceRefreshCheck(models.Model):
    """Per-variant attempt cursor: failed/unlicensed phones cannot starve later rows."""

    variant = models.OneToOneField(DeviceVariant, on_delete=models.CASCADE, related_name="price_refresh_check")
    last_attempted_at = models.DateTimeField(db_index=True)
    last_result = models.CharField(max_length=32, blank=True)

    def __str__(self):
        return f"{self.variant} checked at {self.last_attempted_at}"
