"""Durable filing-email outbox; existing filing/source rows are never modified."""
import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class AlertPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='alert_preference')
    email_enabled = models.BooleanField(default=True)
    unsubscribe_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)


class AlertDelivery(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='alert_deliveries')
    key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    state = models.CharField(max_length=16, default='pending', choices=[(s,s) for s in ('pending','sending','retry','sent','held','cancelled')])
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    lease_until = models.DateTimeField(null=True, blank=True)
    recipient = models.EmailField(blank=True)
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    last_error = models.CharField(max_length=255, blank=True)
    resolution_note = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['state','next_attempt_at'], name='alert_due_idx')]


class AlertEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    filing = models.ForeignKey('filings.Filing', on_delete=models.CASCADE, related_name='alert_events')
    searches = models.ManyToManyField('filings.SavedSearch', related_name='alert_events')
    watches = models.ManyToManyField('filings.IssuerWatch', related_name='alert_events')
    delivery = models.ForeignKey(AlertDelivery, null=True, blank=True, on_delete=models.RESTRICT, related_name='events')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','filing'], name='unique_user_filing_alert')]
        indexes = [models.Index(fields=['user','delivery'], name='alert_unassigned_idx')]


class AlertRun(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    stats = models.JSONField(default=dict)
