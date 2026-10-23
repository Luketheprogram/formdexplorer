"""Operational ingestion state; never substitutes for original filing values."""
from django.db import models
from django.utils import timezone


class IngestionRun(models.Model):
    dataset = models.CharField(max_length=8)
    start_date = models.DateField()
    end_date = models.DateField()
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True)
    stats = models.JSONField(default=dict)


class IngestionJob(models.Model):
    dataset = models.CharField(max_length=8)
    kind = models.CharField(max_length=8)  # index / filing
    key = models.CharField(max_length=64)  # date / accession
    source_date = models.DateField()
    entry = models.JSONField(default=dict)
    state = models.CharField(max_length=16, default="pending")
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    lease_token = models.UUIDField(null=True)
    lease_until = models.DateTimeField(null=True)
    last_error = models.TextField(blank=True)
    outcome = models.CharField(max_length=32, blank=True)
    discovered_count = models.PositiveIntegerField(default=0)
    last_success_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["dataset", "kind", "key"], name="unique_ingestion_job")]
        indexes = [models.Index(fields=["dataset", "kind", "state", "next_attempt_at"], name="ingestion_due_idx")]


class IngestionSource(models.Model):
    """Exact retrieved bytes, including HTML/SGML, with immutable content identity."""
    job = models.ForeignKey(IngestionJob, on_delete=models.PROTECT, related_name="sources")
    url = models.URLField(max_length=500)
    sha256 = models.CharField(max_length=64)
    content = models.BinaryField()
    retrieved_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["job", "url", "sha256"], name="unique_ingestion_source")]
