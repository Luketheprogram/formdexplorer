import django.contrib.postgres.indexes
from django.db import migrations, models


def _slug_name(name: str) -> str:
    import re
    s = (name or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:200] or "person"


def forwards(apps, schema_editor):
    RelatedPerson = apps.get_model("filings", "RelatedPerson")
    for rp in RelatedPerson.objects.all().iterator(chunk_size=1000):
        rp.name_slug = _slug_name(rp.name)
        rp.save(update_fields=["name_slug"])


class Migration(migrations.Migration):
    dependencies = [
        ("filings", "0005_alter_issuerwatch_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="relatedperson",
            name="name_slug",
            field=models.SlugField(blank=True, db_index=True, default="", max_length=200),
        ),
        migrations.AddIndex(
            model_name="relatedperson",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["name"], name="rp_name_trgm", opclasses=["gin_trgm_ops"]
            ),
        ),
        migrations.RunPython(forwards, reverse_code=migrations.RunPython.noop),
    ]
