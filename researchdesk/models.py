"""Research provenance, editorial workflow and private workspace records."""

import hashlib
import json
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

DATASETS = [("d", "Form D"), ("c", "Form C"), ("a", "Reg A"), ("adv", "Form ADV")]


class DisclosureEvidence(models.Model):
    dataset = models.CharField(max_length=3, choices=DATASETS)
    accession = models.CharField(max_length=32)
    cik = models.CharField(max_length=10)
    source_hash = models.CharField(max_length=64)
    source_url = models.URLField(max_length=500)
    accepted_at = models.DateTimeField(null=True, blank=True)
    identity = models.JSONField(default=dict)
    facts = models.JSONField(default=dict)
    references = models.JSONField(default=list)
    extraction_version = models.PositiveIntegerField(default=2)
    extracted_at = models.DateTimeField(default=timezone.now)
    last_checked_at = models.DateTimeField(default=timezone.now, db_index=True)
    source_record_updated_at = models.DateTimeField(null=True, blank=True)
    issues = models.JSONField(default=list)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["dataset", "accession", "source_hash", "extraction_version"],
                name="unique_disclosure_evidence",
            )
        ]
        indexes = [models.Index(fields=["dataset", "accession"])]


class CoverageDay(models.Model):
    dataset = models.CharField(max_length=3, choices=DATASETS)
    day = models.DateField()
    status = models.CharField(
        max_length=16,
        default="unchecked",
        choices=[
            (v, v.title())
            for v in ["unchecked", "complete", "partial", "failed", "closed"]
        ],
    )
    expected = models.PositiveIntegerField(null=True)
    stored = models.PositiveIntegerField(default=0)
    missing = models.JSONField(default=list)
    unexpected = models.JSONField(default=list)
    source_hash = models.CharField(max_length=64, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    checked_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["dataset", "day"], name="unique_coverage_day"
            )
        ]
        ordering = ["-day", "dataset"]


class OfferingLink(models.Model):
    dataset = models.CharField(max_length=3, choices=DATASETS)
    earlier = models.CharField(max_length=32)
    later = models.CharField(max_length=32)
    cik = models.CharField(max_length=10)
    evidence = models.ForeignKey(DisclosureEvidence, on_delete=models.PROTECT)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    note = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["dataset", "earlier", "later"], name="unique_offering_link"
            )
        ]

    def clean(self):
        if self.earlier == self.later:
            raise ValidationError("An offering link needs two different accessions.")
        if (
            self.earlier not in self.evidence.references
            or self.later != self.evidence.accession
            or self.cik != self.evidence.cik
        ):
            raise ValidationError(
                "The stored source must explicitly reference the earlier accession for the same CIK."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Contributor(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=160)
    bio = models.TextField(blank=True)
    source_links = models.JSONField(default=list)
    verified_at = models.DateTimeField(null=True, blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    def clean(self):
        if self.verified_at and (not self.bio.strip() or not self.source_links):
            raise ValidationError(
                "A verified profile needs an actual biography and supporting source links."
            )
        from django.core.validators import URLValidator

        validate = URLValidator(schemes=["https"])
        for link in self.source_links:
            if not isinstance(link, str):
                raise ValidationError("Profile sources must be HTTPS URLs.")
            validate(link)

    def __str__(self):
        return self.name


class ResearchEdition(models.Model):
    series = models.SlugField()
    version = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=220)
    period_start = models.DateField()
    period_end = models.DateField()
    data_as_of = models.DateTimeField()
    snapshot = models.JSONField(default=dict)
    body = models.TextField(help_text="Reviewed research commentary; plain text.")
    author = models.ForeignKey(
        Contributor,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="editions",
    )
    previous = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True
    )
    correction_note = models.TextField(blank=True)
    status = models.CharField(
        max_length=12,
        default="draft",
        choices=[("draft", "Draft"), ("published", "Published")],
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["series", "period_start", "period_end", "version"],
                name="unique_research_edition",
            )
        ]
        ordering = ["-period_end", "-version"]

    @property
    def checksum(self):
        return hashlib.sha256(
            json.dumps(self.snapshot, sort_keys=True, default=str).encode()
        ).hexdigest()

    def clean(self):
        if self.period_end < self.period_start:
            raise ValidationError("The reporting period is reversed.")
        if self.previous_id and (
            self.previous.series != self.series or self.previous.version >= self.version
        ):
            raise ValidationError(
                "The previous edition must belong to this series and have an earlier version."
            )
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if old.status == "published":
                immutable = [
                    "snapshot",
                    "body",
                    "title",
                    "period_start",
                    "period_end",
                    "data_as_of",
                    "version",
                    "series",
                    "author_id",
                    "published_at",
                    "status",
                ]
                if any(getattr(old, f) != getattr(self, f) for f in immutable):
                    raise ValidationError(
                        "Published editions are immutable. Create a corrected edition."
                    )
        if self.status == "published":
            if (
                not self.author_id
                or not self.author.verified_at
                or not self.published_at
            ):
                raise ValidationError(
                    "Publication needs a verified author and publication date."
                )
            if (
                not self.pk
                or not self.reviews.filter(
                    source_checked=True,
                    calculation_checked=True,
                    interpretation_checked=True,
                    reviewer__verified_at__isnull=False,
                ).exists()
            ):
                raise ValidationError(
                    "Publication needs a recorded source, calculation and interpretation review."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class EditorialReview(models.Model):
    edition = models.ForeignKey(
        ResearchEdition, on_delete=models.PROTECT, related_name="reviews"
    )
    reviewer = models.ForeignKey(Contributor, on_delete=models.PROTECT)
    source_checked = models.BooleanField(default=False)
    calculation_checked = models.BooleanField(default=False)
    interpretation_checked = models.BooleanField(default=False)
    sources = models.JSONField(default=list)
    note = models.TextField()
    reviewed_at = models.DateTimeField(default=timezone.now)


class Collection(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="research_collections",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, max_length=2000)
    created_at = models.DateTimeField(default=timezone.now)


class ResearchItem(models.Model):
    collection = models.ForeignKey(
        Collection, on_delete=models.CASCADE, related_name="items"
    )
    dataset = models.CharField(max_length=3, choices=DATASETS)
    reference = models.CharField(max_length=32)
    note = models.TextField(blank=True, max_length=5000)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "dataset", "reference"],
                name="unique_collection_item",
            )
        ]


class ReaderRequest(models.Model):
    kind = models.CharField(
        max_length=12,
        choices=[
            ("correction", "Record correction"),
            ("research", "Research topic"),
            ("usability", "Usability participation"),
        ],
    )
    dataset = models.CharField(max_length=3, choices=DATASETS, blank=True)
    reference = models.CharField(max_length=32, blank=True)
    field = models.CharField(max_length=80, blank=True)
    description = models.TextField(max_length=3000)
    email = models.EmailField(
        blank=True,
        help_text="Optional contact, never published or automatically emailed.",
    )
    consent_to_contact = models.BooleanField(default=False)
    status = models.CharField(
        max_length=12,
        default="new",
        choices=[("new", "New"), ("reviewing", "Reviewing"), ("resolved", "Resolved")],
    )
    created_at = models.DateTimeField(default=timezone.now)


class UsabilitySession(models.Model):
    participant_code = models.CharField(
        max_length=80, help_text="Use a participant code, not a public personal name."
    )
    consented_at = models.DateTimeField()
    device = models.CharField(max_length=120)
    task_results = models.JSONField(
        default=list,
        help_text="Observed tasks, completion, duration and problems. Never synthetic feedback.",
    )
    facilitator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)


class ResearchJob(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True
    )
    request_key = models.UUIDField(null=True, blank=True, unique=True)
    kind = models.CharField(max_length=24)
    params = models.JSONField(default=dict)
    state = models.CharField(max_length=12, default="pending")
    lease = models.UUIDField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    payload = models.BinaryField(null=True, blank=True)
    filename = models.CharField(max_length=180, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    credit_consumed = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["state", "created_at"])]
