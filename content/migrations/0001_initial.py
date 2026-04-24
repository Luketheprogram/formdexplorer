from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies: list = []

    operations = [
        migrations.CreateModel(
            name="Article",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("slug", models.SlugField(max_length=220, unique=True)),
                ("title", models.CharField(max_length=220)),
                ("meta_description", models.CharField(blank=True, default="", max_length=300)),
                ("body", models.TextField(help_text="Markdown")),
                ("published_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-published_at", "-id"]},
        ),
    ]
