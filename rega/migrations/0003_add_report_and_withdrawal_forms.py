from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("rega", "0002_regafilingreview")]
    operations = [migrations.AlterField(
        model_name="form1afiling", name="form_type",
        field=models.CharField(max_length=10, db_index=True, default="1-A", choices=[
            (form, form) for form in ("1-A", "1-A/A", "1-A POS", "1-K", "1-K/A", "1-U", "1-U/A",
                                      "1-Z", "1-Z/A", "1-SA", "1-SA/A", "1-A-W", "1-Z-W", "1-A-W/A", "1-Z-W/A")]))]
