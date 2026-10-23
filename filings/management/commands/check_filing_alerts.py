import json
from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from django.db.models import Count
from django.utils import timezone
from filings.models import AlertDelivery,AlertEvent,AlertRun,SavedSearch


class Command(BaseCommand):
    help='Read-only alert delivery health and queue age; no recipient addresses or email bodies.'
    def handle(self,*args,**opts):
        now=timezone.now();cutoff=now-timedelta(hours=36)
        last=AlertRun.objects.filter(stats__send_enabled=True,finished_at__isnull=False).order_by('-finished_at').first()
        issues=[]
        if not settings.ALERT_EMAIL_ENABLED:issues.append('delivery_disabled')
        if not last or last.finished_at<cutoff:issues.append('missing_or_stale_delivery_run')
        if last and last.stats.get('fatal_error'):issues.append('latest_run_failed')
        if SavedSearch.objects.filter(alerts_enabled=True,user__is_active=True).exclude(user__alert_preference__email_enabled=False).exclude(alert_error='').exists():issues.append('invalid_saved_search')
        if AlertDelivery.objects.filter(state='held').exists():issues.append('held_deliveries')
        if AlertDelivery.objects.filter(state='sending',lease_until__lte=now).exists():issues.append('interrupted_sender')
        if AlertDelivery.objects.filter(state__in=['pending','retry'],created_at__lt=cutoff).exists():issues.append('aged_delivery_backlog')
        from filings.alerts.service import eligible_events
        # Include unbatched overflow; disabled subscriptions are deliberately excluded.
        unbatched=AlertEvent.objects.filter(delivery__isnull=True,created_at__lt=cutoff,user__is_active=True).exclude(user__alert_preference__email_enabled=False)
        if any(eligible_events(uid).filter(pk__in=unbatched.values('pk')).exists() for uid in unbatched.values_list('user_id',flat=True).distinct()):issues.append('aged_match_backlog')
        report={'healthy':not issues,'issues':issues,'states':dict(AlertDelivery.objects.values_list('state').annotate(n=Count('pk'))),'last_delivery_run':last.finished_at.isoformat() if last else None}
        self.stdout.write(json.dumps(report,sort_keys=True))
        if issues:raise CommandError('Filing alert delivery needs attention')
