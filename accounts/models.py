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
    stripe_subscription_id = models.CharField(max_length=128, blank=True, default="")
    subscription_event_created = models.DateTimeField(null=True, blank=True)
    subscription_event_id = models.CharField(max_length=128, blank=True, default="")
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
        return (
            self.is_active
            and self.subscription_status in {"active", "trialing"}
            and self.subscription_tier in {self.SUBSCRIPTION_PRO, self.SUBSCRIPTION_API}
        )

    @property
    def has_api_access(self) -> bool:
        return self.is_paid and self.subscription_tier == self.SUBSCRIPTION_API


class ExportToken(models.Model):
    """One paid grant, usable for one successfully generated CSV or XLSX."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="export_tokens")
    stripe_payment_intent = models.CharField(max_length=128, blank=True, default="")
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["stripe_payment_intent"],
                condition=~models.Q(stripe_payment_intent=""),
                name="unique_export_payment_intent",
            ),
        ]

    @property
    def is_unused(self) -> bool:
        return self.used_at is None

    def consume(self) -> bool:
        """Atomically claim only an unused grant, even from a stale instance."""
        used_at = timezone.now()
        claimed = type(self).objects.filter(pk=self.pk, used_at__isnull=True).update(used_at=used_at)
        if claimed:
            self.used_at = used_at
        return bool(claimed)
