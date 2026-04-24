from django.contrib import admin

from .models import Article


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "published_at", "updated_at")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "slug", "body")
