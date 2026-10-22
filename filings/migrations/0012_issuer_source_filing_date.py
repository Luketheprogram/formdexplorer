from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("filings", "0011_issuer_inferred_website")]
    operations = [migrations.AddField("issuer", "source_filing_date", models.DateField(null=True, blank=True))]
