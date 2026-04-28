from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("filings", "0009_issuer_contact")]

    operations = [
        migrations.AddField(
            model_name="filing",
            name="banker_count",
            field=models.IntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="filing",
            name="banker_names",
            field=models.CharField(blank=True, default="", max_length=500, null=True),
        ),
    ]
