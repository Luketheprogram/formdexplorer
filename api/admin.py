from django.contrib import admin

from .models import ApiKey


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "key_prefix", "usage_count", "monthly_limit", "usage_window_start", "revoked_at")
    search_fields = ("user__email", "key_prefix", "name")
    readonly_fields = ("key_hash", "key_prefix", "usage_count", "usage_window_start")
