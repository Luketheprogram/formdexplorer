import django.contrib.postgres.indexes
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies: list = []

    operations = [
        migrations.CreateModel(
            name="Adviser",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("crd", models.CharField(db_index=True, max_length=20, unique=True)),
                ("sec_file_number", models.CharField(blank=True, db_index=True, default="", max_length=32)),
                ("name", models.CharField(max_length=255)),
                ("name_slug", models.SlugField(db_index=True, max_length=255)),
                ("normalized_name", models.CharField(blank=True, db_index=True, default="", max_length=255)),
                ("street", models.CharField(blank=True, default="", max_length=255)),
                ("city", models.CharField(blank=True, default="", max_length=128)),
                ("state", models.CharField(blank=True, db_index=True, default="", max_length=8)),
                ("zip_code", models.CharField(blank=True, default="", max_length=16)),
                ("phone", models.CharField(blank=True, default="", max_length=32)),
                ("website", models.URLField(blank=True, default="", max_length=300)),
                ("regulatory_aum", models.BigIntegerField(blank=True, db_index=True, null=True)),
                ("discretionary_aum", models.BigIntegerField(blank=True, null=True)),
                ("num_employees", models.IntegerField(blank=True, null=True)),
                ("num_clients", models.IntegerField(blank=True, null=True)),
                ("registration_status", models.CharField(blank=True, default="", max_length=64)),
                ("has_disciplinary", models.BooleanField(default=False)),
                ("last_filed_at", models.DateField(blank=True, null=True)),
                ("raw_data", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddIndex(
            model_name="adviser",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["name"], name="adviser_name_trgm", opclasses=["gin_trgm_ops"]
            ),
        ),
    ]
