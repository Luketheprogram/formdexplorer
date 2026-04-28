import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("filings", "0009_issuer_contact")]

    operations = [
        migrations.CreateModel(
            name="Form1AFiling",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("accession_number", models.CharField(db_index=True, max_length=32, unique=True)),
                ("filing_date", models.DateField(db_index=True)),
                (
                    "form_type",
                    models.CharField(
                        choices=[
                            ("1-A", "1-A"),
                            ("1-A/A", "1-A/A"),
                            ("1-A POS", "1-A POS"),
                            ("1-K", "1-K"),
                            ("1-K/A", "1-K/A"),
                            ("1-U", "1-U"),
                            ("1-U/A", "1-U/A"),
                            ("1-Z", "1-Z"),
                            ("1-Z/A", "1-Z/A"),
                        ],
                        db_index=True,
                        default="1-A",
                        max_length=10,
                    ),
                ),
                ("is_amendment", models.BooleanField(default=False)),
                ("tier", models.CharField(blank=True, db_index=True, default="", max_length=8)),
                ("total_offering_amount", models.BigIntegerField(blank=True, db_index=True, null=True)),
                ("total_amount_sold", models.BigIntegerField(blank=True, null=True)),
                ("price_per_security", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("security_type", models.CharField(blank=True, default="", max_length=128)),
                ("over_allotment", models.BigIntegerField(blank=True, null=True)),
                ("jurisdictions", models.CharField(blank=True, default="", max_length=255)),
                ("total_assets", models.BigIntegerField(blank=True, null=True)),
                ("total_liabilities", models.BigIntegerField(blank=True, null=True)),
                ("total_revenues", models.BigIntegerField(blank=True, null=True)),
                ("net_income", models.BigIntegerField(blank=True, null=True)),
                ("cash_equivalents", models.BigIntegerField(blank=True, null=True)),
                ("raw_xml", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "issuer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rega_filings",
                        to="filings.issuer",
                    ),
                ),
            ],
            options={"ordering": ["-filing_date", "-id"]},
        ),
        migrations.AddIndex(
            model_name="form1afiling",
            index=models.Index(fields=["-filing_date"], name="rega_filing_date_desc_idx"),
        ),
        migrations.AddIndex(
            model_name="form1afiling",
            index=models.Index(fields=["tier", "-filing_date"], name="rega_tier_date_idx"),
        ),
    ]
