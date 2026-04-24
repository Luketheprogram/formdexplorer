from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import ExportToken, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "subscription_tier", "is_staff", "is_active", "date_joined")
    list_filter = ("subscription_tier", "is_staff", "is_active")
    search_fields = ("email", "stripe_customer_id")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Subscription", {"fields": ("stripe_customer_id", "subscription_status", "subscription_tier")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )


@admin.register(ExportToken)
class ExportTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "stripe_payment_intent", "used_at", "created_at")
    search_fields = ("user__email", "stripe_payment_intent")
