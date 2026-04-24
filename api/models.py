import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

KEY_PREFIX = "fde_"
MONTHLY_LIMIT = 10_000
WINDOW_DAYS = 30


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ApiKey(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_keys"
    )
    name = models.CharField(max_length=80, default="Default")
    key_hash = models.CharField(max_length=64, unique=True, db_index=True)
    key_prefix = models.CharField(max_length=12, help_text="First chars shown for identification")
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    # Rolling 30-day counter
    usage_window_start = models.DateTimeField(null=True, blank=True)
    usage_count = models.IntegerField(default=0)
    monthly_limit = models.IntegerField(default=MONTHLY_LIMIT)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.key_prefix}…)"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @classmethod
    def generate(cls, user, name: str = "Default") -> tuple["ApiKey", str]:
        raw = KEY_PREFIX + secrets.token_urlsafe(32)
        obj = cls.objects.create(
            user=user,
            name=name[:80] or "Default",
            key_hash=_hash_key(raw),
            key_prefix=raw[:10],
        )
        return obj, raw

    @classmethod
    def lookup(cls, raw: str) -> "ApiKey | None":
        if not raw:
            return None
        try:
            return cls.objects.select_related("user").get(
                key_hash=_hash_key(raw), revoked_at__isnull=True
            )
        except cls.DoesNotExist:
            return None

    def revoke(self) -> None:
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked_at"])

    @transaction.atomic
    def consume(self) -> tuple[bool, int]:
        """Atomically increment usage counter. Returns (allowed, remaining)."""
        locked = ApiKey.objects.select_for_update().get(pk=self.pk)
        now = timezone.now()
        if locked.usage_window_start is None or (
            now - locked.usage_window_start > timedelta(days=WINDOW_DAYS)
        ):
            locked.usage_window_start = now
            locked.usage_count = 0
        if locked.usage_count >= locked.monthly_limit:
            return False, 0
        locked.usage_count += 1
        locked.save(update_fields=["usage_window_start", "usage_count"])
        return True, locked.monthly_limit - locked.usage_count
