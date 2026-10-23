"""Queue once per user/accession; never automatically repeat an ambiguous SMTP send."""
import smtplib
from contextlib import contextmanager
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, get_connection
from django.core.validators import validate_email
from django.db import connection, transaction
from django.db.models import F, Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from filings.models import SavedSearch, IssuerWatch, Filing, AlertPreference, AlertEvent, AlertDelivery, AlertRun
from filings.search import build_filing_query
from filings.search_params import SearchValidationError

MAX_ATTEMPTS = 6
LEASE = timedelta(minutes=10)
LOCK_KEY = 7042310902


@contextmanager
def worker_lock():
    if connection.vendor != 'postgresql':
        raise RuntimeError('Alert workers require PostgreSQL for cross-process locking')
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s)', [LOCK_KEY])
        if not cursor.fetchone()[0]:
            raise RuntimeError('Another alert worker is active')
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s)', [LOCK_KEY])


def delivery_configuration():
    if not settings.ALERT_EMAIL_ENABLED:
        raise RuntimeError('Customer alert delivery is disabled (ALERT_EMAIL_ENABLED=False)')
    if settings.EMAIL_BACKEND != 'django.core.mail.backends.smtp.EmailBackend' or not settings.EMAIL_HOST:
        raise RuntimeError('Alerts require a configured SMTP backend; console/file/test backends cannot mark mail sent')
    if not (settings.EMAIL_USE_TLS or getattr(settings, 'EMAIL_USE_SSL', False)):
        raise RuntimeError('Alerts require encrypted SMTP')
    if urlsplit(settings.SITE_URL).scheme != 'https':
        raise RuntimeError('Alerts require an HTTPS SITE_URL')
    validate_email(settings.DEFAULT_FROM_EMAIL)


def preference(user_id):
    return AlertPreference.objects.get_or_create(user_id=user_id)[0]


def source_queryset(source):
    if isinstance(source, SavedSearch):
        return build_filing_query(source.params), 'searches'
    return Filing.objects.filter(issuer_id=source.issuer_id), 'watches'


def discover(*, kinds=('search','watch'), dry_run=False, limit=None):
    """Scan import timestamps, not SEC filing dates. No advancing cursor can skip a late commit.

    A bounded pass excludes already-associated matches BEFORE applying its limit,
    so the next pass continues overflow. Legacy subscriptions initialize at now.
    """
    limit = limit or settings.ALERT_MATCH_LIMIT
    stats = dict(matches=0, sources=0, initialized=0, invalid=0)
    cutoff = timezone.now()
    classes = ([SavedSearch] if 'search' in kinds else []) + ([IssuerWatch] if 'watch' in kinds else [])
    for model in classes:
        for source in model.objects.filter(alerts_enabled=True, user__is_active=True).iterator():
            # Lock ordering shared with unsubscribe: preference, then source.
            with transaction.atomic():
                if dry_run:
                    pref = AlertPreference.objects.filter(user_id=source.user_id).first()
                else:
                    preference(source.user_id)
                    pref = AlertPreference.objects.select_for_update().get(user_id=source.user_id)
                if pref and not pref.email_enabled:
                    continue
                if not dry_run:
                    source = model.objects.select_for_update().filter(pk=source.pk, alerts_enabled=True).first()
                    if source is None:
                        continue
                try:
                    qs, relation = source_queryset(source)
                except SearchValidationError:
                    stats['invalid'] += 1
                    if not dry_run:
                        model.objects.filter(pk=source.pk).update(alert_error='Invalid search filters; recreate this saved search.')
                    continue
                if source.alerts_started_at is None:
                    stats['initialized'] += 1
                    if not dry_run:
                        model.objects.filter(pk=source.pk).update(alerts_started_at=cutoff)
                    # Never send the historical archive on activation.
                    continue
                qs = qs.filter(created_at__gte=source.alerts_started_at, created_at__lte=cutoff).exclude(
                    **{f'alert_events__{relation}': source}).order_by('created_at','pk')
                ids = list(qs.values_list('pk', flat=True)[:limit])
                stats['matches'] += len(ids)
                stats['sources'] += 1
                if dry_run:
                    continue
                for filing_id in ids:
                    event, _ = AlertEvent.objects.get_or_create(user_id=source.user_id, filing_id=filing_id)
                    getattr(event, relation).add(source)
                if isinstance(source, SavedSearch):
                    SavedSearch.objects.filter(pk=source.pk).update(last_checked_at=cutoff, alert_error='')
    return stats


def eligible_events(user_id):
    return AlertEvent.objects.filter(user_id=user_id).filter(
        Q(searches__alerts_enabled=True, searches__alerts_started_at__lte=F('filing__created_at')) |
        Q(watches__alerts_enabled=True, watches__alerts_started_at__lte=F('filing__created_at'))
    ).distinct()


def batch_events():
    batches = 0
    users = AlertEvent.objects.filter(delivery__isnull=True).values_list('user_id',flat=True).distinct()
    for user_id in users:
        with transaction.atomic():
            pref = AlertPreference.objects.select_for_update().get(user_id=user_id)
            if not pref.email_enabled:
                continue
            # One pending digest per user per pass. Overflow survives for the next run.
            if AlertDelivery.objects.filter(user_id=user_id, state__in=['pending','retry','sending','held']).exists():
                continue
            ids = list(eligible_events(user_id).filter(delivery__isnull=True).order_by('pk').values_list('pk',flat=True)[:settings.ALERT_BATCH_SIZE])
            if ids:
                delivery = AlertDelivery.objects.create(user_id=user_id)
                AlertEvent.objects.filter(pk__in=ids,delivery__isnull=True).update(delivery=delivery)
                batches += 1
    return batches


def claim_delivery(pk, now=None):
    now = now or timezone.now()
    return bool(AlertDelivery.objects.filter(pk=pk, state__in=['pending','retry'],
        attempts__lt=MAX_ATTEMPTS, next_attempt_at__lte=now).update(
            state='sending', attempts=F('attempts')+1, lease_until=now+LEASE, updated_at=now))


def recover_expired():
    # An expired sender may have already handed the message to SMTP. Holding it
    # deliberately favors no duplicate over an unsupported exactly-once claim.
    now = timezone.now()
    return AlertDelivery.objects.filter(state='sending',lease_until__lte=now).update(
        state='held',last_error='Acceptance unknown after interrupted worker; inspect provider logs',
        lease_until=None, updated_at=now)


def failed(delivery, *, retryable, reason):
    delivery.state = 'retry' if retryable and delivery.attempts < MAX_ATTEMPTS else 'held'
    delivery.last_error = reason
    delivery.next_attempt_at = timezone.now() + timedelta(minutes=min(1440,15*2**(delivery.attempts-1)))
    delivery.lease_until = None
    delivery.save()


def rejection(exc):
    """Only explicit pre-acceptance rejections are safe to retry automatically."""
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [v[0] for v in exc.recipients.values()]
        return bool(codes) and all(400 <= c < 500 for c in codes), 'SMTP recipient rejected'
    if isinstance(exc, (smtplib.SMTPDataError, smtplib.SMTPSenderRefused)):
        return 400 <= exc.smtp_code < 500, f'SMTP rejected message ({exc.smtp_code})'
    return False, 'SMTP acceptance unknown; inspect provider logs before retrying'


def deliver(pk):
    delivery_configuration()
    if not claim_delivery(pk):
        return 'skipped'
    # Persist the claim BEFORE touching SMTP. A crash/commit failure leaves a
    # sending record, which recovery holds instead of automatically resending.
    initial = AlertDelivery.objects.get(pk=pk)
    smtp = None
    with transaction.atomic():
        pref = AlertPreference.objects.select_for_update().get(user_id=initial.user_id)
        delivery = AlertDelivery.objects.select_for_update().select_related('user').get(pk=pk)
        if delivery.state != 'sending':
            return 'skipped'
        if not pref.email_enabled or not delivery.user.is_active:
            delivery.state = 'cancelled'
        events = list(eligible_events(delivery.user_id).filter(delivery=delivery).select_related('filing','filing__issuer').order_by('pk'))
        if not events:
            delivery.state = 'cancelled'
        if delivery.state == 'cancelled':
            delivery.lease_until = None
            delivery.save()
            return 'cancelled'
        delivery.recipient = delivery.user.email
        try:
            validate_email(delivery.recipient)
        except ValidationError:
            failed(delivery,retryable=False,reason='Recipient email is invalid')
            return delivery.state
        unsubscribe = settings.SITE_URL + reverse('filings:alert_unsubscribe',args=[pref.unsubscribe_token])
        one_click = settings.SITE_URL + reverse('filings:alert_unsubscribe_one_click',args=[pref.unsubscribe_token])
        delivery.subject = f'[Form D Explorer] {len(events)} new filing match(es)'
        delivery.body = render_to_string('emails/filing_alert_digest.txt', {
            'events':events,'site_url':settings.SITE_URL,'unsubscribe_url':unsubscribe})
        delivery.save()
        try:
            smtp = get_connection(timeout=settings.ALERT_EMAIL_TIMEOUT, fail_silently=False)
            smtp.open()
        except Exception as exc:
            if smtp is not None:
                try:
                    smtp.close()
                except Exception:
                    pass
            code = getattr(exc,'smtp_code',None)
            failed(delivery, retryable=not(code and code>=500), reason=f'SMTP connection failed ({type(exc).__name__})')
            return delivery.state
        try:
            mail = EmailMessage(delivery.subject,delivery.body,settings.DEFAULT_FROM_EMAIL,[delivery.recipient],
                connection=smtp,headers={
                    'Message-ID':f'<filing-alert-{delivery.key}@{urlsplit(settings.SITE_URL).hostname}>',
                    'List-Unsubscribe':f'<{one_click}>',
                    'List-Unsubscribe-Post':'List-Unsubscribe=One-Click',
                    'Auto-Submitted':'auto-generated',
                })
            if mail.send(fail_silently=False) != 1:
                failed(delivery,retryable=False,reason='SMTP acceptance unconfirmed; inspect provider logs')
            else:
                delivery.state='sent'
                delivery.sent_at=timezone.now()
                delivery.lease_until=None
                delivery.last_error=''
                delivery.save()
                IssuerWatch.objects.filter(alert_events__in=events).update(last_notified_at=delivery.sent_at)
        except Exception as exc:
            retryable, reason = rejection(exc)
            failed(delivery,retryable=retryable,reason=reason)
        finally:
            # QUIT can fail after successful acceptance; that must never undo sent.
            try:
                smtp.close()
            except Exception:
                pass
        return delivery.state


def process(*, send=False, dry_run=False, kinds=('search','watch')):
    if send:
        delivery_configuration()
        from filings.ingest.monitoring import freshness_report
        if freshness_report()['datasets']['d']['issues']:
            raise RuntimeError('Form D ingestion is unhealthy; alert discovery/send deferred')
    if dry_run:
        return discover(kinds=kinds,dry_run=True)
    with worker_lock():
        run = AlertRun.objects.create()
        stats = {}
        try:
            stats['recovered_to_hold'] = recover_expired()
            stats.update(discover(kinds=kinds))
            stats['batched'] = batch_events()
            if send:
                due = AlertDelivery.objects.filter(state__in=['pending','retry'],next_attempt_at__lte=timezone.now()).order_by('next_attempt_at','pk')
                for pk in list(due.values_list('pk',flat=True)[:settings.ALERT_SEND_LIMIT]):
                    state = deliver(pk)
                    stats[state] = stats.get(state,0)+1
            return stats
        except Exception:
            stats['fatal_error'] = True
            raise
        finally:
            stats['send_enabled'] = send
            run.stats=stats
            run.finished_at=timezone.now()
            run.save()
