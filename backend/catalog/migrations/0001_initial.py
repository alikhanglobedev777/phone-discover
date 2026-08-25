# Generated manually for the initial Mobile Discovery catalog.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Brand",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("slug", models.SlugField(max_length=140, unique=True)),
                ("logo_url", models.URLField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Device",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=180)),
                ("slug", models.SlugField(max_length=220, unique=True)),
                ("summary", models.TextField(blank=True)),
                ("release_date", models.DateField(blank=True, null=True)),
                ("operating_system", models.CharField(blank=True, max_length=80)),
                ("specifications", models.JSONField(blank=True, default=dict)),
                ("is_published", models.BooleanField(default=False)),
                ("last_verified_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("brand", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="devices", to="catalog.brand")),
            ],
            options={"ordering": ["-release_date", "name"]},
        ),
        migrations.CreateModel(
            name="DeviceVariant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("ram_gb", models.PositiveIntegerField(default=8)),
                ("storage_gb", models.PositiveIntegerField(default=128)),
                ("battery_mah", models.PositiveIntegerField(blank=True, null=True)),
                ("display_refresh_hz", models.PositiveIntegerField(blank=True, null=True)),
                ("chipset", models.CharField(blank=True, max_length=160)),
                ("camera_score", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("gaming_score", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("battery_score", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="variants", to="catalog.device")),
            ],
            options={"ordering": ["device__name", "-ram_gb", "-storage_gb"]},
        ),
        migrations.CreateModel(
            name="MarketOffer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("country_code", models.CharField(max_length=2)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("seller_name", models.CharField(max_length=160)),
                ("product_url", models.URLField()),
                ("is_affiliate", models.BooleanField(default=False)),
                ("is_available", models.BooleanField(default=True)),
                ("checked_at", models.DateTimeField(auto_now=True)),
                ("variant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="offers", to="catalog.devicevariant")),
            ],
            options={"ordering": ["price"]},
        ),
        migrations.AddConstraint(
            model_name="devicevariant",
            constraint=models.UniqueConstraint(fields=("device", "name"), name="unique_device_variant"),
        ),
        migrations.AddIndex(
            model_name="device",
            index=models.Index(fields=["is_published", "brand"], name="catalog_dev_is_publ_8bb8e6_idx"),
        ),
        migrations.AddIndex(
            model_name="device",
            index=models.Index(fields=["name"], name="catalog_dev_name_8ca8f7_idx"),
        ),
        migrations.AddIndex(
            model_name="marketoffer",
            index=models.Index(fields=["country_code", "currency", "price"], name="catalog_mar_country_4d31f0_idx"),
        ),
        migrations.AddIndex(
            model_name="marketoffer",
            index=models.Index(fields=["is_available", "country_code"], name="catalog_mar_is_avai_6eb1d4_idx"),
        ),
    ]
