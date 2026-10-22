"""Signed HTTP delivery tests; only dj-stripe's remote mirror calls are stubbed.

These fixtures are not a substitute for delivery from an authenticated Stripe
sandbox. Signature verification, event persistence and application receivers
run unchanged against the test database.
"""
import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from djstripe.models import Event

from accounts.models import ExportToken

SECRET = 'whsec_local_regression_fixture'


def event_for(user_id, event_id='evt_delivery', event_type='checkout.session.completed', **obj):
    return {'id': event_id, 'object': 'event', 'api_version': '2025-03-31.basil',
            'created': int(time.time()), 'livemode': False, 'pending_webhooks': 1,
            'request': None, 'type': event_type, 'data': {'object': {
                'id': 'cs_local_fixture', 'object': 'checkout.session', 'mode': 'payment',
                'payment_status': 'paid', 'payment_intent': 'pi_local_fixture',
                'metadata': {'user_id': str(user_id), 'plan_key': 'export'}, **obj}}}


def deliver(client, event, secret=SECRET, timestamp=None):
    body = json.dumps(event).encode()
    timestamp = int(time.time()) if timestamp is None else timestamp
    signature = hmac.new(secret.encode(), str(timestamp).encode() + b'.' + body, hashlib.sha256).hexdigest()
    return client.post('/stripe/webhook/', body, content_type='application/json',
                       HTTP_STRIPE_SIGNATURE=f't={timestamp},v1={signature}')


class RemoteMirrorStubs:
    def setUp(self):
        super().setUp()
        # dj-stripe separately mirrors customers, sessions and subscriptions from
        # its API. Do not replace the event model or any application receiver.
        for target in ('djstripe.models.base.StripeModel._find_owner_account',
                       'djstripe.event_handlers._handle_crud_like_event'):
            stub = patch(target, return_value=None)
            stub.start()
            self.addCleanup(stub.stop)
        self.user = get_user_model().objects.create_user(email='webhooks@example.com')


@override_settings(STRIPE_LIVE_MODE=False, DJSTRIPE_WEBHOOK_SECRET=SECRET, SECURE_SSL_REDIRECT=False)
class SignedWebhookTests(RemoteMirrorStubs, TestCase):
    def test_paid_checkout_duplicate_and_async_delivery_grant_once(self):
        event = event_for(self.user.pk)
        self.assertEqual(deliver(self.client, event).status_code, 200)
        ExportToken.objects.get().consume()
        self.assertEqual(deliver(self.client, event).status_code, 200)
        event.update(id='evt_async', type='checkout.session.async_payment_succeeded')
        self.assertEqual(deliver(self.client, event).status_code, 200)
        self.assertEqual(ExportToken.objects.count(), 1)
        self.assertFalse(ExportToken.objects.get().is_unused)
        self.assertEqual(Event.objects.count(), 2)

    def test_bad_signature_expired_signature_and_wrong_mode_do_not_write(self):
        event = event_for(self.user.pk)
        self.assertEqual(deliver(self.client, event, secret='wrong').status_code, 400)
        self.assertEqual(deliver(self.client, event, timestamp=int(time.time()) - 600).status_code, 400)
        event['livemode'] = True
        self.assertEqual(deliver(self.client, event).status_code, 400)
        self.assertFalse(Event.objects.exists())
        self.assertFalse(ExportToken.objects.exists())

    def test_handler_failure_rolls_back_event_and_credit_and_retry_succeeds(self):
        event = event_for(self.user.pk)
        # Fail after the grant to prove the outer transaction covers both writes.
        with patch('accounts.models.User.save', side_effect=RuntimeError('temporary write failure')):
            with self.assertLogs('subscriptions.views', level='ERROR'):
                self.assertEqual(deliver(self.client, event).status_code, 500)
        self.assertFalse(Event.objects.exists())
        self.assertFalse(ExportToken.objects.exists())
        self.assertEqual(deliver(self.client, event).status_code, 200)
        self.assertEqual(ExportToken.objects.count(), 1)

    def test_subscription_transitions_and_reordered_delivery(self):
        for index, status in enumerate(('active', 'past_due', 'active', 'canceled')):
            event = event_for(self.user.pk, event_id=f'evt_sub_{index}',
                              event_type='customer.subscription.updated', id='sub_fixture',
                              object='subscription', status=status,
                              metadata={'user_id': str(self.user.pk), 'plan_key': 'api'})
            event['created'] += index
            self.assertEqual(deliver(self.client, event).status_code, 200)
            self.user.refresh_from_db()
            self.assertEqual(self.user.has_api_access, status == 'active')
        event.update(id='evt_late', created=event['created'] - 10)
        event['data']['object']['status'] = 'active'
        self.assertEqual(deliver(self.client, event).status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_paid)


@override_settings(STRIPE_LIVE_MODE=False, DJSTRIPE_WEBHOOK_SECRET=SECRET, SECURE_SSL_REDIRECT=False)
class ConcurrentWebhookTests(RemoteMirrorStubs, TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_duplicate_deliveries_on_separate_connections(self):
        barrier = Barrier(2)
        insert_barrier = Barrier(2)
        event = event_for(self.user.pk)
        save = Event.save

        def simultaneous_insert(instance, *args, **kwargs):
            if instance._state.adding:
                insert_barrier.wait(timeout=10)
            return save(instance, *args, **kwargs)

        def send(_):
            try:
                barrier.wait(timeout=10)
                return deliver(Client(), event).status_code
            finally:
                connections.close_all()

        with patch.object(Event, 'save', simultaneous_insert):
            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses = list(pool.map(send, range(2)))
        self.assertEqual(statuses, [200, 200])
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(ExportToken.objects.count(), 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_distinct_delivery_ids_for_one_payment_grant_once(self):
        barrier = Barrier(2)
        def send(index):
            try:
                event = event_for(self.user.pk, event_id=f'evt_distinct_{index}')
                barrier.wait(timeout=10)
                return deliver(Client(), event).status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(send, range(2))), [200, 200])
        self.assertEqual(Event.objects.count(), 2)
        self.assertEqual(ExportToken.objects.count(), 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_concurrent_subscription_updates_keep_newest_status(self):
        barrier = Barrier(2)
        events = [event_for(self.user.pk, event_id=f'evt_status_{i}',
                    event_type='customer.subscription.updated', id='sub_fixture', object='subscription',
                    status=status, metadata={'user_id': str(self.user.pk), 'plan_key': 'pro'})
                  for i, status in enumerate(('active', 'unpaid'))]
        events[1]['created'] = events[0]['created'] + 1
        def send(event):
            try:
                barrier.wait(timeout=10)
                return deliver(Client(), event).status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(send, events)), [200, 200])
        self.user.refresh_from_db()
        self.assertEqual(self.user.subscription_status, 'unpaid')
        self.assertFalse(self.user.is_paid)
