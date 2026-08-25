import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "catalog",
            "0002_rename_catalog_dev_is_publ_8bb8e6_idx_catalog_dev_is_publ_df8385_idx_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="official_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="device",
            name="primary_image_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="device",
            name="status",
            field=models.CharField(
                choices=[
                    ("rumored", "Rumored"),
                    ("announced", "Announced"),
                    ("available", "Available"),
                    ("discontinued", "Discontinued"),
                ],
                db_index=True,
                default="available",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="DeviceImage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("image_url", models.URLField(max_length=1000)),
                ("alt_text", models.CharField(blank=True, max_length=200)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("is_primary", models.BooleanField(default=False)),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="catalog.device",
                    ),
                ),
            ],
            options={"ordering": ["-is_primary", "sort_order", "id"]},
        ),
        migrations.CreateModel(
            name="SpecificationSection",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=140)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="specification_sections",
                        to="catalog.device",
                    ),
                ),
            ],
            options={"ordering": ["sort_order", "id"]},
        ),
        migrations.CreateModel(
            name="SpecificationItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("label", models.CharField(max_length=120)),
                ("value", models.TextField()),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                (
                    "section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="catalog.specificationsection",
                    ),
                ),
            ],
            options={"ordering": ["sort_order", "id"]},
        ),
        migrations.AddConstraint(
            model_name="deviceimage",
            constraint=models.UniqueConstraint(
                fields=("device", "image_url"),
                name="unique_device_image_url",
            ),
        ),
        migrations.AddIndex(
            model_name="deviceimage",
            index=models.Index(
                fields=["device", "is_primary", "sort_order"],
                name="catalog_image_device_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="specificationsection",
            constraint=models.UniqueConstraint(
                fields=("device", "slug"),
                name="unique_device_spec_section",
            ),
        ),
        migrations.AddIndex(
            model_name="specificationsection",
            index=models.Index(
                fields=["device", "sort_order"],
                name="catalog_spec_device_order_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="specificationitem",
            constraint=models.UniqueConstraint(
                fields=("section", "label"),
                name="unique_section_spec_label",
            ),
        ),
        migrations.AddIndex(
            model_name="specificationitem",
            index=models.Index(
                fields=["section", "sort_order"],
                name="catalog_item_section_order_idx",
            ),
        ),
    ]
