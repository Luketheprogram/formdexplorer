from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.utils.text import slugify

from filings.models import normalize_issuer_name


class Adviser(models.Model):
    """Form ADV-registered investment adviser. CRD is the canonical id."""

    crd = models.CharField(max_length=20, unique=True, db_index=True)
    sec_file_number = models.CharField(max_length=32, blank=True, default="", db_index=True)
    name = models.CharField(max_length=255)
    name_slug = models.SlugField(max_length=255, db_index=True)
    normalized_name = models.CharField(max_length=255, db_index=True, blank=True, default="")

    street = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=128, blank=True, default="")
    state = models.CharField(max_length=8, blank=True, default="", db_index=True)
    zip_code = models.CharField(max_length=16, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    website = models.URLField(blank=True, default="", max_length=300)

    regulatory_aum = models.BigIntegerField(null=True, blank=True, db_index=True)
    discretionary_aum = models.BigIntegerField(null=True, blank=True)
    num_employees = models.IntegerField(null=True, blank=True)
    num_clients = models.IntegerField(null=True, blank=True)

    registration_status = models.CharField(max_length=64, blank=True, default="")
    has_disciplinary = models.BooleanField(default=False)

    last_filed_at = models.DateField(null=True, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            GinIndex(fields=["name"], name="adviser_name_trgm", opclasses=["gin_trgm_ops"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} (CRD {self.crd})"

    def save(self, *args, **kwargs):
        if not self.name_slug and self.name:
            self.name_slug = slugify(self.name)[:250] or "adviser"
        self.normalized_name = normalize_issuer_name(self.name)
        super().save(*args, **kwargs)

    @property
    def iapd_url(self) -> str:
        return f"https://adviserinfo.sec.gov/firm/summary/{self.crd}"
