from django.db import models


class Article(models.Model):
    slug = models.SlugField(max_length=220, unique=True)
    title = models.CharField(max_length=220)
    meta_description = models.CharField(max_length=300, blank=True, default="")
    body = models.TextField(help_text="Markdown")
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-id"]

    def __str__(self) -> str:
        return self.title

    @property
    def is_published(self) -> bool:
        return self.published_at is not None
