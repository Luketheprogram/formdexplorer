import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("filings", "0009_issuer_contact")]

    operations = [
        migrations.CreateModel(
            name="CrowdfundingFiling",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("accession_number", models.CharField(db_index=True, max_length=32, unique=True)),
                ("filing_date", models.DateField(db_index=True)),
                (
                    "form_type",
                    models.CharField(
                        choices=[
                            ("C", "C"),
                            ("C/A", "C/A"),
                            ("C-U", "C-U"),
                            ("C-AR", "C-AR"),
                            ("C-AR/A", "C-AR/A"),
                            ("C-TR", "C-TR"),
                            ("C-W", "C-W"),
                        ],
                        db_index=True,
                        default="C",
                        max_length=10,
                    ),
                ),
                ("is_amendment", models.BooleanField(default=False)),
                ("intermediary_name", models.CharField(blank=True, default="", max_length=255)),
                ("intermediary_cik", models.CharField(blank=True, db_index=True, default="", max_length=10)),
                ("target_offering_amount", models.BigIntegerField(blank=True, null=True)),
                ("maximum_offering_amount", models.BigIntegerField(blank=True, db_index=True, null=True)),
                ("offering_deadline", models.DateField(blank=True, null=True)),
                ("security_type", models.CharField(blank=True, default="", max_length=128)),
                ("price_per_security", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("oversubscription_accepted", models.BooleanField(blank=True, null=True)),
                ("total_assets", models.BigIntegerField(blank=True, null=True)),
                ("cash_equivalents", models.BigIntegerField(blank=True, null=True)),
                ("short_term_debt", models.BigIntegerField(blank=True, null=True)),
                ("long_term_debt", models.BigIntegerField(blank=True, null=True)),
                ("revenues", models.BigIntegerField(blank=True, null=True)),
                ("cost_of_goods_sold", models.BigIntegerField(blank=True, null=True)),
                ("taxes_paid", models.BigIntegerField(blank=True, null=True)),
                ("net_income", models.BigIntegerField(blank=True, null=True)),
                ("raw_xml", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "issuer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="crowdfunding_filings",
                        to="filings.issuer",
                    ),
                ),
            ],
            options={"ordering": ["-filing_date", "-id"]},
        ),
        migrations.AddIndex(
            model_name="crowdfundingfiling",
            index=models.Index(fields=["-filing_date"], name="cf_filing_date_desc_idx"),
        ),
        migrations.AddIndex(
            model_name="crowdfundingfiling",
            index=models.Index(fields=["intermediary_cik", "-filing_date"], name="cf_intermediary_idx"),
        ),
    ]
