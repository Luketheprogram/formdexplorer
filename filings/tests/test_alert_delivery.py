import smtplib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from filings.models import (Issuer,Filing,SavedSearch,IssuerWatch,AlertPreference,AlertEvent,AlertDelivery,AlertRun)
from filings.alerts.service import (discover,batch_events,claim_delivery,deliver,recover_expired,worker_lock,process,preference,MAX_ATTEMPTS)

SMTP_SETTINGS=dict(ALERT_EMAIL_ENABLED=True,EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
    EMAIL_HOST='smtp.example.test',EMAIL_USE_TLS=True,SITE_URL='https://formdexplorer.com')


class Fixture:
    def make(self):
        self.user=get_user_model().objects.create_user(email='researcher@example.test',password='test-only-password')
        self.issuer=Issuer.objects.create(cik='123',name='Example Issuer',state='CA')
        self.start=timezone.now()-timedelta(days=2)
        self.search=SavedSearch.objects.create(user=self.user,name='California',params={'state':['CA','NY']},alerts_started_at=self.start)
        self.watch=IssuerWatch.objects.create(user=self.user,issuer=self.issuer,alerts_started_at=self.start)
        self.pref=preference(self.user.pk)
    def filing(self,n=1):
        return Filing.objects.create(issuer=self.issuer,accession_number=f'0000000123-26-{n:06d}',filing_date=timezone.now().date()-timedelta(days=365),total_offering_amount=0)
    def queued(self):
        self.filing();discover();batch_events();return AlertDelivery.objects.get()


class DiscoveryTests(Fixture,TestCase):
    def setUp(self):self.make()
    def test_overlapping_searches_and_watch_create_one_event(self):
        f=self.filing()
        SavedSearch.objects.create(user=self.user,name='Also California',params={'state':['CA']},alerts_started_at=self.start)
        discover();discover();batch_events();batch_events()
        e=AlertEvent.objects.get(filing=f)
        self.assertEqual(e.searches.count(),2);self.assertEqual(e.watches.count(),1)
        self.assertEqual(AlertDelivery.objects.count(),1)
    def test_late_import_matches_despite_old_filing_date(self):
        f=self.filing();discover();self.assertTrue(AlertEvent.objects.filter(filing=f).exists())
    def test_bounded_discovery_continues_past_limit(self):
        for n in range(1,106):self.filing(n)
        discover(limit=40);discover(limit=40);discover(limit=40)
        self.assertEqual(AlertEvent.objects.count(),105)
        self.assertEqual(self.search.alert_events.count(),105)
    def test_import_with_earlier_timestamp_seen_on_next_pass(self):
        discover();f=self.filing();Filing.objects.filter(pk=f.pk).update(created_at=self.start+timedelta(minutes=1))
        discover();self.assertTrue(AlertEvent.objects.filter(filing=f).exists())
    def test_legacy_baseline_never_emails_history(self):
        self.search.alerts_started_at=None;self.search.save();self.watch.alerts_started_at=None;self.watch.save()
        self.filing();stats=discover();self.assertEqual(stats['initialized'],2);self.assertEqual(AlertEvent.objects.count(),0)
        self.filing(2);discover();self.assertEqual(AlertEvent.objects.count(),1)
    def test_preview_has_no_writes_or_recipient_output(self):
        self.filing();self.pref.delete()
        out=StringIO();call_command('process_filing_alerts',stdout=out)
        self.assertEqual(AlertPreference.objects.count(),0);self.assertEqual(AlertEvent.objects.count(),0);self.assertEqual(AlertRun.objects.count(),0)
        self.assertNotIn(self.user.email,out.getvalue())
    def test_invalid_search_is_isolated_and_visible(self):
        self.search.params={'min_amount':'bad'};self.search.save();self.filing()
        stats=discover();self.search.refresh_from_db();self.assertEqual(stats['invalid'],1)
        self.assertTrue(self.search.alert_error);self.assertEqual(AlertEvent.objects.count(),1)
    @override_settings(ALERT_BATCH_SIZE=2)
    def test_digest_overflow_survives_for_later_batch(self):
        for n in range(1,6):self.filing(n)
        discover();batch_events();self.assertEqual(AlertDelivery.objects.get().events.count(),2)
        AlertDelivery.objects.update(state='sent');batch_events()
        self.assertEqual(AlertDelivery.objects.count(),2);self.assertEqual(AlertEvent.objects.filter(delivery=None).count(),1)
    def test_deleted_sources_cancel_queued_email(self):
        d=self.queued();self.search.delete();self.watch.delete()
        with override_settings(**SMTP_SETTINGS),patch('filings.alerts.service.get_connection') as smtp:
            self.assertEqual(deliver(d.pk),'cancelled');smtp.assert_not_called()
    def test_inactive_user_is_not_queued(self):
        self.user.is_active=False;self.user.save();self.filing();discover();self.assertFalse(AlertEvent.objects.exists())
    def test_disabled_delivery_does_not_queue_or_call_smtp(self):
        with override_settings(ALERT_EMAIL_ENABLED=False),patch('filings.alerts.service.get_connection') as smtp:
            with self.assertRaises(CommandError):call_command('process_filing_alerts',send=True)
            smtp.assert_not_called();self.assertFalse(AlertEvent.objects.exists());self.assertFalse(AlertRun.objects.exists())


@override_settings(**SMTP_SETTINGS)
class DeliveryTests(Fixture,TestCase):
    def setUp(self):self.make();self.d=self.queued()
    def backend(self):
        b=Mock();b.send_messages.return_value=1;return b
    def test_success_is_deduplicated_across_repeated_runs(self):
        b=self.backend()
        with patch('filings.alerts.service.get_connection',return_value=b):
            self.assertEqual(deliver(self.d.pk),'sent');self.assertEqual(deliver(self.d.pk),'skipped')
        discover();batch_events();self.assertEqual(AlertDelivery.objects.count(),1)
        b.send_messages.assert_called_once();message=b.send_messages.call_args.args[0][0]
        self.assertEqual(message.to,[self.user.email]);self.assertIn('List-Unsubscribe-Post',message.extra_headers)
        self.assertIn('/filing/0000000123-26-000001/',message.body)
        self.assertNotIn('None',message.body);self.assertIn('unsubscribe',message.body)
    def test_transient_rejection_retries_with_same_message_id(self):
        b=self.backend();b.send_messages.side_effect=[smtplib.SMTPDataError(451,b'try later'),1]
        with patch('filings.alerts.service.get_connection',return_value=b):
            self.assertEqual(deliver(self.d.pk),'retry')
            self.assertEqual(deliver(self.d.pk),'skipped')
            AlertDelivery.objects.filter(pk=self.d.pk).update(next_attempt_at=timezone.now()-timedelta(seconds=1))
            self.assertEqual(deliver(self.d.pk),'sent')
        headers=[c.args[0][0].extra_headers['Message-ID'] for c in b.send_messages.call_args_list]
        self.assertEqual(headers[0],headers[1]);self.d.refresh_from_db();self.assertEqual(self.d.attempts,2)
    def test_connection_failure_retries_without_sending(self):
        b=self.backend();b.open.side_effect=ConnectionRefusedError()
        with patch('filings.alerts.service.get_connection',return_value=b):self.assertEqual(deliver(self.d.pk),'retry')
        b.send_messages.assert_not_called()
    def test_disconnect_after_possible_acceptance_is_held_not_retried(self):
        b=self.backend();b.send_messages.side_effect=smtplib.SMTPServerDisconnected('possibly accepted')
        with patch('filings.alerts.service.get_connection',return_value=b):
            self.assertEqual(deliver(self.d.pk),'held');self.assertEqual(deliver(self.d.pk),'skipped')
        self.assertEqual(b.send_messages.call_count,1)
    def test_permanent_recipient_rejection_is_held_and_error_redacted(self):
        b=self.backend();b.send_messages.side_effect=smtplib.SMTPRecipientsRefused({self.user.email:(550,b'no mailbox')})
        with patch('filings.alerts.service.get_connection',return_value=b):self.assertEqual(deliver(self.d.pk),'held')
        self.d.refresh_from_db();self.assertNotIn(self.user.email,self.d.last_error)
    def test_zero_messages_is_not_success(self):
        b=self.backend();b.send_messages.return_value=0
        with patch('filings.alerts.service.get_connection',return_value=b):self.assertEqual(deliver(self.d.pk),'held')
    def test_quit_failure_does_not_undo_success(self):
        b=self.backend();b.close.side_effect=TimeoutError()
        with patch('filings.alerts.service.get_connection',return_value=b):self.assertEqual(deliver(self.d.pk),'sent')
    def test_attempt_budget_holds_repeated_failures(self):
        AlertDelivery.objects.filter(pk=self.d.pk).update(attempts=MAX_ATTEMPTS-1)
        b=self.backend();b.open.side_effect=ConnectionRefusedError()
        with patch('filings.alerts.service.get_connection',return_value=b):self.assertEqual(deliver(self.d.pk),'held')
    def test_expired_sending_claim_is_held(self):
        self.assertTrue(claim_delivery(self.d.pk));AlertDelivery.objects.filter(pk=self.d.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
        self.assertEqual(recover_expired(),1);self.d.refresh_from_db();self.assertEqual(self.d.state,'held')
    def test_console_backend_cannot_mark_sent(self):
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend'):
            with self.assertRaises(RuntimeError):deliver(self.d.pk)
        self.d.refresh_from_db();self.assertEqual(self.d.state,'pending')
    def test_global_optout_cancels_before_smtp(self):
        self.pref.email_enabled=False;self.pref.save()
        with patch('filings.alerts.service.get_connection') as b:self.assertEqual(deliver(self.d.pk),'cancelled');b.assert_not_called()
    def test_paused_source_excluded_while_other_source_still_matches(self):
        self.search.alerts_enabled=False;self.search.save()
        b=self.backend()
        with patch('filings.alerts.service.get_connection',return_value=b):self.assertEqual(deliver(self.d.pk),'sent')


class UnsubscribeTests(Fixture,TestCase):
    def setUp(self):self.make();self.d=self.queued()
    def test_get_and_head_do_not_unsubscribe(self):
        url=reverse('filings:alert_unsubscribe',args=[self.pref.unsubscribe_token])
        response=self.client.get(url);self.pref.refresh_from_db();self.assertTrue(self.pref.email_enabled)
        self.assertEqual(response.status_code,200);self.assertIn('noindex',response['X-Robots-Tag']);self.assertIn('no-store',response['Cache-Control'])
        self.assertEqual(response['Referrer-Policy'],'no-referrer')
    def test_form_requires_csrf_but_one_click_requires_capability_and_post(self):
        client=Client(enforce_csrf_checks=True)
        url=reverse('filings:alert_unsubscribe',args=[self.pref.unsubscribe_token])
        self.assertEqual(client.post(url).status_code,403)
        one=reverse('filings:alert_unsubscribe_one_click',args=[self.pref.unsubscribe_token])
        self.assertEqual(client.get(one).status_code,405)
        self.assertEqual(client.post(one).status_code,400)
        self.assertEqual(client.post(one,{'List-Unsubscribe':'One-Click'}).status_code,200)
        self.assertEqual(client.post(one,{'List-Unsubscribe':'One-Click'}).status_code,200)
        self.pref.refresh_from_db();self.d.refresh_from_db();self.assertFalse(self.pref.email_enabled);self.assertEqual(self.d.state,'cancelled')
    def test_resume_rotates_token_and_skips_paused_history(self):
        old=self.pref.unsubscribe_token
        self.client.post(reverse('filings:alert_unsubscribe',args=[old]))
        self.filing(2);self.client.force_login(self.user)
        self.client.post(reverse('filings:alert_preferences'),{'enabled':'1'})
        self.pref.refresh_from_db();self.assertNotEqual(old,self.pref.unsubscribe_token)
        self.assertEqual(self.client.get(reverse('filings:alert_unsubscribe',args=[old])).status_code,404)
        discover();self.assertEqual(AlertEvent.objects.count(),1)
        self.filing(3);discover();self.assertEqual(AlertEvent.objects.count(),2)
    def test_other_user_cannot_toggle_sources(self):
        other=get_user_model().objects.create_user(email='other@example.test',password='test')
        self.client.force_login(other)
        for name,pk in [('filings:saved_search_alert_toggle',self.search.pk),('filings:watch_alert_toggle',self.watch.pk)]:
            self.assertEqual(self.client.post(reverse(name,args=[pk])).status_code,404)
    def test_pause_keeps_search_and_watch_and_is_post_only(self):
        self.client.force_login(self.user)
        for name,source in [('filings:saved_search_alert_toggle',self.search),('filings:watch_alert_toggle',self.watch)]:
            url=reverse(name,args=[source.pk]);self.assertEqual(self.client.get(url).status_code,405)
            self.assertEqual(self.client.post(url).status_code,302);source.refresh_from_db();self.assertFalse(source.alerts_enabled)
        self.assertEqual(SavedSearch.objects.count(),1);self.assertEqual(IssuerWatch.objects.count(),1)
    def test_invalid_capability_cannot_change_preferences(self):
        import uuid
        self.assertEqual(self.client.post(reverse('filings:alert_unsubscribe_one_click',args=[uuid.uuid4()]),{'List-Unsubscribe':'One-Click'}).status_code,404)
        self.pref.refresh_from_db();self.assertTrue(self.pref.email_enabled)


@skipUnlessDBFeature('has_select_for_update')
class ConcurrencyTests(Fixture,TransactionTestCase):
    def setUp(self):self.make();self.d=self.queued()
    def test_two_workers_claim_only_once(self):
        barrier=Barrier(2)
        def claim():
            close_old_connections()
            try:barrier.wait();return claim_delivery(self.d.pk)
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:claim(),range(2)))
        self.assertEqual(sorted(results),[False,True]);self.d.refresh_from_db();self.assertEqual(self.d.attempts,1)
    def test_worker_lock_blocks_other_connection(self):
        def attempt():
            close_old_connections()
            try:
                with worker_lock():return True
            except RuntimeError:return False
            finally:close_old_connections()
        with worker_lock(),ThreadPoolExecutor(max_workers=1) as pool:self.assertFalse(pool.submit(attempt).result())
    def test_preference_lock_serializes_unsubscribe_with_send(self):
        from threading import Event
        from filings.alerts.views import opt_out
        entered=Event();done=Event()
        def unsubscribe():
            close_old_connections()
            try:entered.set();opt_out(self.pref.unsubscribe_token);done.set()
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                AlertPreference.objects.select_for_update().get(pk=self.pref.pk)
                future=pool.submit(unsubscribe);self.assertTrue(entered.wait(2));self.assertFalse(done.wait(.1))
            future.result(timeout=5)
        self.d.refresh_from_db();self.assertEqual(self.d.state,'cancelled')
    def test_accepted_then_database_rollback_remains_uncertain(self):
        # Simulate a worker dying after the external side effect, before commit.
        with override_settings(**SMTP_SETTINGS):
            backend=Mock();backend.send_messages.side_effect=KeyboardInterrupt()
            with patch('filings.alerts.service.get_connection',return_value=backend):
                with self.assertRaises(KeyboardInterrupt):deliver(self.d.pk)
        self.d.refresh_from_db();self.assertEqual(self.d.state,'sending')
        AlertDelivery.objects.filter(pk=self.d.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
        recover_expired();self.d.refresh_from_db();self.assertEqual(self.d.state,'held')

@skipUnlessDBFeature('has_select_for_update')
@override_settings(**SMTP_SETTINGS)
class WorkerIntegrationTests(Fixture,TransactionTestCase):
    def setUp(self):self.make()
    @patch('filings.ingest.monitoring.freshness_report',return_value={'datasets':{'d':{'issues':[]}}})
    def test_one_recipient_failure_does_not_stop_next_recipient(self,health):
        self.filing()
        other=get_user_model().objects.create_user(email='second@example.test',password='test')
        IssuerWatch.objects.create(user=other,issuer=self.issuer,alerts_started_at=self.start)
        first=Mock();first.send_messages.side_effect=smtplib.SMTPDataError(451,b'retry')
        second=Mock();second.send_messages.return_value=1
        with patch('filings.alerts.service.get_connection',side_effect=[first,second]):stats=process(send=True)
        self.assertEqual(stats['retry'],1);self.assertEqual(stats['sent'],1)
        self.assertEqual(AlertEvent.objects.count(),2);self.assertTrue(AlertRun.objects.get().stats['send_enabled'])
    @patch('filings.ingest.monitoring.freshness_report',return_value={'datasets':{'d':{'issues':['stale']}}})
    def test_stale_ingestion_defers_customer_mail_and_preserves_queue(self,health):
        with patch('filings.alerts.service.get_connection') as smtp:
            with self.assertRaises(RuntimeError):process(send=True)
            smtp.assert_not_called();self.assertFalse(AlertRun.objects.exists())
    def test_held_resolution_requires_evidence_and_sends_nothing(self):
        d=self.queued();AlertDelivery.objects.filter(pk=d.pk).update(state='held')
        with patch('filings.alerts.service.get_connection') as smtp:
            with self.assertRaises(CommandError):call_command('resolve_alert_delivery',d.pk,outcome='not-accepted',note='short',stdout=StringIO())
            call_command('resolve_alert_delivery',d.pk,outcome='accepted',note='Provider log confirms accepted message ID',stdout=StringIO())
            smtp.assert_not_called()
        d.refresh_from_db();self.assertEqual(d.state,'sent');self.assertTrue(d.sent_at)
    def test_health_detects_unbatched_overflow(self):
        f=self.filing();discover()
        AlertEvent.objects.update(created_at=timezone.now()-timedelta(days=3))
        out=StringIO()
        with self.assertRaises(CommandError):call_command('check_filing_alerts',stdout=out)
        self.assertIn('aged_match_backlog',out.getvalue())
    def test_user_deletion_does_not_get_blocked_by_own_outbox(self):
        self.queued();self.user.delete();self.assertFalse(AlertDelivery.objects.exists());self.assertFalse(AlertEvent.objects.exists())


class AlertMonitorRegressionTests(Fixture, TestCase):
    def setUp(self): self.make()
    def test_paused_and_inactive_users_do_not_raise_invalid_search_alarm(self):
        self.search.alert_error='Invalid filters'; self.search.save()
        def issues():
            out=StringIO()
            with self.assertRaises(CommandError): call_command('check_filing_alerts',stdout=out)
            return out.getvalue()
        self.assertIn('invalid_saved_search',issues())
        self.pref.email_enabled=False; self.pref.save()
        self.assertNotIn('invalid_saved_search',issues())
        self.pref.email_enabled=True; self.pref.save()
        self.user.is_active=False; self.user.save()
        self.assertNotIn('invalid_saved_search',issues())
