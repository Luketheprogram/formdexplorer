from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    SUBSCRIPTION_FREE = "free"
    SUBSCRIPTION_PRO = "pro"
    SUBSCRIPTION_API = "api"
    SUBSCRIPTION_CHOICES = [
        (SUBSCRIPTION_FREE, "Free"),
        (SUBSCRIPTION_PRO, "Pro Monthly"),
        (SUBSCRIPTION_API, "API Access"),
    ]

    email = models.EmailField(unique=True, db_index=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    stripe_customer_id = models.CharField(max_length=64, blank=True, default="")
    subscription_status = models.CharField(max_length=32, blank=True, default="")
    subscription_tier = models.CharField(
        max_length=16, choices=SUBSCRIPTION_CHOICES, default=SUBSCRIPTION_FREE
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    def __str__(self) -> str:
        return self.email

    @property
    def is_paid(self) -> bool:
        return self.subscription_tier in {self.SUBSCRIPTION_PRO, self.SUBSCRIPTION_API}


class ExportToken(models.Model):
    """One-time CSV export grant (from the $15 one-time purchase)."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="export_tokens")
    stripe_payment_intent = models.CharField(max_length=128, blank=True, default="")
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_unused(self) -> bool:
        return self.used_at is None

    def consume(self) -> None:
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])
