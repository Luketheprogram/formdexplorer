from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("filings", "0008_issuerview")]

    operations = [
        migrations.AddField(
            model_name="issuer",
            name="website",
            field=models.URLField(blank=True, default="", max_length=300),
        ),
        migrations.AddField(
            model_name="issuer",
            name="contact_email",
            field=models.EmailField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="issuer",
            name="enriched_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
