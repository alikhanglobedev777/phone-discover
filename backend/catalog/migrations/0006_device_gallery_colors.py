from django.core import validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("catalog", "0005_web_researched_catalog")]

    operations = [
        migrations.CreateModel(
            name="DeviceColor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("hex_code", models.CharField(blank=True, max_length=7, help_text="Optional representative swatch. Leave blank if the finish cannot be represented accurately.", validators=[validators.RegexValidator("^#[0-9A-Fa-f]{6}$", "Use a six-digit hex color, e.g. #8B263E.")])),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="colors", to="catalog.device")),
            ],
            options={"ordering": ["sort_order", "id"]},
        ),
        migrations.AddConstraint(
            model_name="devicecolor", constraint=models.UniqueConstraint(fields=("device", "name"), name="unique_device_finish")
        ),
        migrations.AddField(
            model_name="deviceimage", name="view",
            field=models.CharField(choices=[("unspecified", "Product photo / angle unknown"), ("front", "Front"), ("back", "Back"), ("side", "Side"), ("detail", "Detail")], default="unspecified", max_length=12),
        ),
        migrations.AddField(
            model_name="deviceimage", name="color",
            field=models.ForeignKey(blank=True, help_text="Set only for a photo of this exact finish. Leave blank for generic/unidentified photos.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="photos", to="catalog.devicecolor"),
        ),
    ]
