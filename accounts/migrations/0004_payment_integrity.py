from django.db import migrations, models


def check_duplicate_payments(apps, schema_editor):
    Token = apps.get_model("accounts", "ExportToken")
    duplicate = (Token.objects.using(schema_editor.connection.alias)
                 .exclude(stripe_payment_intent="")
                 .values("stripe_payment_intent").annotate(n=models.Count("id"))
                 .filter(n__gt=1).exists())
    if duplicate:
        raise RuntimeError(
            "Duplicate export payment intents require manual reconciliation before migration; "
            "no export credits have been deleted or merged."
        )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_alter_exporttoken_id")]
    operations = [
        migrations.AddField("user", "stripe_subscription_id", models.CharField(max_length=128, blank=True, default="")),
        migrations.AddField("user", "subscription_event_created", models.DateTimeField(null=True, blank=True)),
        migrations.AddField("user", "subscription_event_id", models.CharField(max_length=128, blank=True, default="")),
        migrations.RunPython(check_duplicate_payments, migrations.RunPython.noop),
        migrations.AddConstraint("exporttoken", models.UniqueConstraint(
            fields=("stripe_payment_intent",), condition=~models.Q(stripe_payment_intent=""),
            name="unique_export_payment_intent",
        )),
    ]
