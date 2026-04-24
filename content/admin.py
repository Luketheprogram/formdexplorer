from django.contrib import admin

from .models import Article, NewsletterSubscriber


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "published_at", "updated_at")
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "slug", "body")


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "created_at", "confirmed_at", "unsubscribed_at")
    search_fields = ("email",)
