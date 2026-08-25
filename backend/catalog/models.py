from django.db import models


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


class DeviceImage(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="images")
    image_url = models.URLField(max_length=1000)
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
