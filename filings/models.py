import re

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.utils.text import slugify

_ENTITY_SUFFIX_RE = re.compile(
    r"\b(l\.?l\.?c\.?|l\.?p\.?|inc\.?|corp(?:oration)?|co\.?|ltd\.?|llp|gp|fund|"
    r"partners|partnership|holdings|group|capital|trust|the)\b",
    re.IGNORECASE,
)
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


def normalize_issuer_name(name: str) -> str:
    """Lowercase, strip legal-entity suffixes and punctuation so name-only
    matches can link CIKs that are really the same underlying company."""
    if not name:
        return ""
    s = name.lower()
    s = _ENTITY_SUFFIX_RE.sub(" ", s)
    s = _NON_WORD_RE.sub(" ", s)
    return " ".join(s.split())[:255]


class Issuer(models.Model):
    cik = models.CharField(max_length=10, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    name_slug = models.SlugField(max_length=255, db_index=True)
    normalized_name = models.CharField(max_length=255, db_index=True, blank=True, default="")
    entity_type = models.CharField(max_length=128, blank=True, default="")
    jurisdiction = models.CharField(max_length=64, blank=True, default="")
    year_of_incorporation = models.CharField(max_length=16, blank=True, default="")
    street = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=128, blank=True, default="")
    state = models.CharField(max_length=8, blank=True, default="", db_index=True)
    zip_code = models.CharField(max_length=16, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            GinIndex(fields=["name"], name="issuer_name_trgm", opclasses=["gin_trgm_ops"]),
            models.Index(fields=["state"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} (CIK {self.cik})"

    def save(self, *args, **kwargs):
        if not self.name_slug and self.name:
            self.name_slug = slugify(self.name)[:250] or "issuer"
        self.normalized_name = normalize_issuer_name(self.name)
        super().save(*args, **kwargs)

    @property
    def url_slug(self) -> str:
        return f"{self.name_slug}-{self.cik}"


class Filing(models.Model):
    FORM_D = "D"
    FORM_D_A = "D/A"
    FORM_TYPE_CHOICES = [(FORM_D, "D"), (FORM_D_A, "D/A")]

    accession_number = models.CharField(max_length=32, unique=True, db_index=True)
    issuer = models.ForeignKey(Issuer, on_delete=models.CASCADE, related_name="filings")
    filing_date = models.DateField(db_index=True)
    form_type = models.CharField(max_length=8, choices=FORM_TYPE_CHOICES, default=FORM_D)
    is_amendment = models.BooleanField(default=False)

    offering_type = models.CharField(max_length=128, blank=True, default="")
    total_offering_amount = models.BigIntegerField(null=True, blank=True, db_index=True)
    total_amount_sold = models.BigIntegerField(null=True, blank=True)
    minimum_investment = models.BigIntegerField(null=True, blank=True)
    num_investors = models.IntegerField(null=True, blank=True)
    sales_commission = models.BigIntegerField(null=True, blank=True)
    finders_fees = models.BigIntegerField(null=True, blank=True)
    industry_group = models.CharField(max_length=128, blank=True, default="", db_index=True)

    raw_xml = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-filing_date", "-id"]
        indexes = [
            models.Index(fields=["-filing_date"]),
            models.Index(fields=["industry_group", "-filing_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.accession_number} ({self.form_type})"

    @property
    def edgar_url(self) -> str:
        acc = self.accession_number.replace("-", "")
        return (
            f"https://www.sec.gov/Archives/edgar/data/{int(self.issuer.cik)}/"
            f"{acc}/{self.accession_number}-index.htm"
        )


class IssuerWatch(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="watches"
    )
    issuer = models.ForeignKey(
        "filings.Issuer", on_delete=models.CASCADE, related_name="watchers"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("user", "issuer")]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user_id} watches {self.issuer_id}"


class SavedSearch(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_searches"
    )
    name = models.CharField(max_length=120)
    params = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.name}"


class RelatedPerson(models.Model):
    RELATIONSHIP_CHOICES = [
        ("Executive Officer", "Executive Officer"),
        ("Director", "Director"),
        ("Promoter", "Promoter"),
    ]
    filing = models.ForeignKey(Filing, on_delete=models.CASCADE, related_name="related_persons")
    name = models.CharField(max_length=255)
    name_slug = models.SlugField(max_length=200, blank=True, default="", db_index=True)
    relationship = models.CharField(max_length=64, blank=True, default="")
    city = models.CharField(max_length=128, blank=True, default="")
    state = models.CharField(max_length=8, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["filing"]),
            GinIndex(fields=["name"], name="rp_name_trgm", opclasses=["gin_trgm_ops"]),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.name_slug and self.name:
            self.name_slug = slugify(self.name)[:195] or "person"
        super().save(*args, **kwargs)
