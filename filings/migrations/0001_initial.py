import django.contrib.postgres.indexes
import django.contrib.postgres.operations
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies: list = []

    operations = [
        django.contrib.postgres.operations.TrigramExtension(),
        migrations.CreateModel(
            name="Issuer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("cik", models.CharField(db_index=True, max_length=10, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("name_slug", models.SlugField(db_index=True, max_length=255)),
                ("entity_type", models.CharField(blank=True, default="", max_length=128)),
                ("jurisdiction", models.CharField(blank=True, default="", max_length=64)),
                ("year_of_incorporation", models.CharField(blank=True, default="", max_length=16)),
                ("street", models.CharField(blank=True, default="", max_length=255)),
                ("city", models.CharField(blank=True, default="", max_length=128)),
                ("state", models.CharField(blank=True, db_index=True, default="", max_length=8)),
                ("zip_code", models.CharField(blank=True, default="", max_length=16)),
                ("phone", models.CharField(blank=True, default="", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddIndex(
            model_name="issuer",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["name"], name="issuer_name_trgm", opclasses=["gin_trgm_ops"]
            ),
        ),
        migrations.AddIndex(
            model_name="issuer",
            index=models.Index(fields=["state"], name="filings_iss_state_idx"),
        ),
        migrations.CreateModel(
            name="Filing",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("accession_number", models.CharField(db_index=True, max_length=32, unique=True)),
                ("filing_date", models.DateField(db_index=True)),
                ("form_type", models.CharField(choices=[("D", "D"), ("D/A", "D/A")], default="D", max_length=8)),
                ("is_amendment", models.BooleanField(default=False)),
                ("offering_type", models.CharField(blank=True, default="", max_length=128)),
                ("total_offering_amount", models.BigIntegerField(blank=True, db_index=True, null=True)),
                ("total_amount_sold", models.BigIntegerField(blank=True, null=True)),
                ("minimum_investment", models.BigIntegerField(blank=True, null=True)),
                ("num_investors", models.IntegerField(blank=True, null=True)),
                ("sales_commission", models.BigIntegerField(blank=True, null=True)),
                ("finders_fees", models.BigIntegerField(blank=True, null=True)),
                ("industry_group", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("raw_xml", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "issuer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="filings",
                        to="filings.issuer",
                    ),
                ),
            ],
            options={"ordering": ["-filing_date", "-id"]},
        ),
        migrations.AddIndex(
            model_name="filing",
            index=models.Index(fields=["-filing_date"], name="filings_fil_date_desc_idx"),
        ),
        migrations.AddIndex(
            model_name="filing",
            index=models.Index(fields=["industry_group", "-filing_date"], name="filings_fil_ind_date_idx"),
        ),
        migrations.CreateModel(
            name="RelatedPerson",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("relationship", models.CharField(blank=True, default="", max_length=64)),
                ("city", models.CharField(blank=True, default="", max_length=128)),
                ("state", models.CharField(blank=True, default="", max_length=8)),
                (
                    "filing",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="related_persons",
                        to="filings.filing",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="relatedperson",
            index=models.Index(fields=["filing"], name="filings_rp_filing_idx"),
        ),
    ]
