from django.db import migrations


class Migration(migrations.Migration):
    """0006 already created the GinIndex; this stub keeps model-state and
    database-state aligned after moving the index declaration from AddIndex
    into Meta.indexes."""

    dependencies = [
        ("filings", "0006_related_person_trigram"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[],
        ),
    ]
