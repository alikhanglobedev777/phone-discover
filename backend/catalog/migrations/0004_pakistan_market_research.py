"""Pakistan condition/PTA price observations and source-backed research staging.

Intentionally additive: legacy MarketOffer rows and existing Device/DeviceVariant
records are retained without a lossy data migration.
"""

import django.db.models.deletion
import django.core.validators
import django.utils.timezone
from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0003_rich_catalog_specs"),
    ]

    operations = [
        migrations.CreateModel(
            name="ResearchSource",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("url", models.URLField(max_length=1000, unique=True)),
                ("title", models.CharField(max_length=255)),
                ("publisher", models.CharField(blank=True, max_length=160)),
                ("source_type", models.CharField(choices=[
                    ("manufacturer", "Manufacturer"), ("retailer", "Retailer"),
                    ("classified", "Classified listing"), ("review", "Independent review"),
                    ("other", "Other"),
                ], default="other", max_length=20)),
                ("reuse_status", models.CharField(choices=[
                    ("unknown", "Not assessed"), ("permitted", "Permitted for intended use"),
                    ("restricted", "Restricted"),
                ], default="unknown", max_length=20)),
                ("reuse_notes", models.TextField(blank=True)),
                ("last_checked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-updated_at", "id"]},
        ),
        migrations.CreateModel(
            name="DeviceClaim",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("field_path", models.CharField(max_length=160)),
                ("proposed_value", models.JSONField()),
                ("status", models.CharField(choices=[
                    ("pending", "Pending review"), ("verified", "Verified"),
                    ("rejected", "Rejected"),
                ], db_index=True, default="pending", max_length=12)),
                ("observed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("review_notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="research_claims", to="catalog.device")),
                ("source", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="claims", to="catalog.researchsource")),
            ],
            options={"ordering": ["-observed_at", "-id"]},
        ),
        migrations.CreateModel(
            name="MarketPriceObservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("condition", models.CharField(choices=[
                    ("box_pack", "New / box pack"), ("open_box", "Open box"),
                    ("used", "Used"), ("refurbished", "Refurbished"),
                ], max_length=14)),
                ("grade", models.CharField(blank=True, choices=[
                    ("excellent", "Excellent"), ("good", "Good"), ("fair", "Fair"),
                ], default="", max_length=12)),
                ("pta_status", models.CharField(choices=[
                    ("approved", "PTA approved (reported or verified)"), ("non_pta", "Non-PTA"),
                    ("cpid", "CPID (not official PTA approval)"),
                    ("patched", "Patched (not official PTA approval)"),
                    ("unknown", "Unknown"),
                ], default="unknown", max_length=12)),
                ("pta_verification", models.CharField(choices=[
                    ("unknown", "Not checked"), ("reported", "Seller/source claim"),
                    ("checked", "Independently checked"),
                ], default="unknown", max_length=12)),
                ("city", models.CharField(blank=True, max_length=100)),
                ("seller_name", models.CharField(blank=True, max_length=160)),
                ("listing_url", models.URLField(blank=True, max_length=1000)),
                ("listing_status", models.CharField(choices=[
                    ("unknown", "Unknown"), ("active", "Active when checked"),
                    ("ended", "Listing ended"),
                ], default="unknown", max_length=12)),
                ("battery_health_percent", models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ("price_min_pkr", models.DecimalField(decimal_places=2, max_digits=12)),
                ("price_max_pkr", models.DecimalField(decimal_places=2, max_digits=12)),
                ("observed_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("verification_status", models.CharField(choices=[
                    ("pending", "Pending review"), ("verified", "Verified"),
                    ("rejected", "Rejected"),
                ], db_index=True, default="pending", max_length=12)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("source", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="price_observations", to="catalog.researchsource")),
                ("variant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pk_market_prices", to="catalog.devicevariant")),
            ],
            options={"ordering": ["-observed_at", "-id"]},
        ),
        migrations.CreateModel(
            name="IngestionCandidate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("candidate_type", models.CharField(choices=[
                    ("device", "Phone identity"), ("specifications", "Phone specifications"),
                    ("price", "Market price"),
                ], max_length=20)),
                ("payload", models.JSONField(default=dict)),
                ("fingerprint", models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ("status", models.CharField(choices=[
                    ("pending", "Pending review"), ("approved", "Approved for ingestion"),
                    ("rejected", "Rejected"), ("ingested", "Ingested"),
                ], db_index=True, default="pending", max_length=12)),
                ("review_notes", models.TextField(blank=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("matched_device", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ingestion_candidates", to="catalog.device")),
                ("source", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ingestion_candidates", to="catalog.researchsource")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="deviceclaim",
            index=models.Index(fields=["device", "status"], name="cat_claim_device_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="deviceclaim",
            constraint=models.CheckConstraint(condition=~Q(status="verified") | Q(reviewed_at__isnull=False), name="cat_claim_verified_reviewed"),
        ),
        migrations.AddIndex(
            model_name="marketpriceobservation",
            index=models.Index(fields=["variant", "verification_status", "observed_at"], name="cat_pkprice_variant_review_idx"),
        ),
        migrations.AddIndex(
            model_name="marketpriceobservation",
            index=models.Index(fields=["condition", "pta_status", "city"], name="cat_pkprice_condition_idx"),
        ),
        migrations.AddConstraint(
            model_name="marketpriceobservation",
            constraint=models.CheckConstraint(condition=Q(price_min_pkr__gt=0), name="cat_pkprice_positive_min"),
        ),
        migrations.AddConstraint(
            model_name="marketpriceobservation",
            constraint=models.CheckConstraint(condition=Q(price_max_pkr__gte=F("price_min_pkr")), name="cat_pkprice_ordered_range"),
        ),
        migrations.AddConstraint(
            model_name="marketpriceobservation",
            constraint=models.CheckConstraint(condition=Q(battery_health_percent__isnull=True) | Q(battery_health_percent__lte=100), name="cat_pkprice_battery_limit"),
        ),
        migrations.AddConstraint(
            model_name="marketpriceobservation",
            constraint=models.CheckConstraint(condition=Q(grade="") | Q(condition__in=["used", "refurbished"]), name="cat_pkprice_grade_condition"),
        ),
        migrations.AddConstraint(
            model_name="marketpriceobservation",
            constraint=models.CheckConstraint(condition=~Q(pta_verification="checked") | ~Q(pta_status="unknown"), name="cat_pkprice_checked_pta_known"),
        ),
        migrations.AddConstraint(
            model_name="marketpriceobservation",
            constraint=models.CheckConstraint(condition=~Q(verification_status="verified") | Q(reviewed_at__isnull=False), name="cat_pkprice_verified_reviewed"),
        ),
        migrations.AddConstraint(
            model_name="marketpriceobservation",
            constraint=models.CheckConstraint(condition=~Q(verification_status="verified") | Q(source__isnull=False) | ~Q(notes=""), name="cat_pkprice_verified_evidence"),
        ),
        migrations.AddIndex(
            model_name="ingestioncandidate",
            index=models.Index(fields=["status", "candidate_type"], name="cat_ingest_status_type_idx"),
        ),
        migrations.AddConstraint(
            model_name="ingestioncandidate",
            constraint=models.CheckConstraint(condition=Q(status="pending") | Q(reviewed_at__isnull=False), name="cat_ingest_reviewed_time"),
        ),
    ]
