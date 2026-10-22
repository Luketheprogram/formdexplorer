from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import resolve, reverse

from accounts.models import ExportToken
from subscriptions.signals import on_checkout_completed, on_subscription_active, on_payment_failed


@override_settings(STRIPE_LIVE_MODE=False)
class PaymentIntegrityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="payments@example.com")
        self.now = timezone.now()

    def event(self, obj, seconds=0, event_id="evt_test"):
        obj.setdefault("metadata", {"user_id": str(self.user.pk), "plan_key": "pro"})
        return SimpleNamespace(id=event_id, livemode=False, created=self.now + timedelta(seconds=seconds), data={"object": obj})

    def subscription(self, status, **kwargs):
        return self.event({"id": "sub_test", "status": status}, **kwargs)

    def test_checkout_return_routes_are_not_interpreted_as_plan_names(self):
        for name in ("checkout_success", "checkout_cancel"):
            self.assertEqual(resolve(reverse(f"subscriptions:{name}")).url_name, name)

    def test_status_matrix_revokes_access_and_recovery_restores_it(self):
        for index, status in enumerate(["active", "past_due", "trialing", "unpaid", "active",
                                        "paused", "canceled", "incomplete", "incomplete_expired", ""]):
            with self.subTest(status=status):
                on_subscription_active(self.subscription(status, seconds=index, event_id=f"evt_{index}"))
                self.user.refresh_from_db()
                self.assertEqual(self.user.is_paid, status in {"active", "trialing"})
                if not self.user.is_paid:
                    self.assertEqual(self.user.subscription_tier, "free")

    def test_stale_and_same_second_active_events_cannot_restore_revoked_access(self):
        on_subscription_active(self.subscription("unpaid", seconds=10, event_id="evt_unpaid"))
        for seconds in (1, 10):
            with patch("subscriptions.signals.stripe.Subscription.retrieve", return_value={
                "id": "sub_test", "status": "unpaid",
                "metadata": {"user_id": str(self.user.pk), "plan_key": "pro"},
            }):
                on_subscription_active(self.subscription("active", seconds=seconds))
            self.user.refresh_from_db()
            self.assertFalse(self.user.is_paid)
        on_subscription_active(self.subscription("active", seconds=11, event_id="evt_recovered"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_paid)

    def test_same_second_first_payment_reconciles_to_active(self):
        on_subscription_active(self.subscription("incomplete", event_id="evt_created"))
        with patch("subscriptions.signals.stripe.Subscription.retrieve", return_value={
            "id": "sub_test", "status": "active",
            "metadata": {"user_id": str(self.user.pk), "plan_key": "pro"},
        }):
            on_subscription_active(self.subscription("active", event_id="evt_updated"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_paid)

    def test_old_subscription_cancellation_does_not_revoke_replacement(self):
        on_subscription_active(self.subscription("active"))
        on_subscription_active(self.event({"id": "sub_old", "status": "canceled"}, seconds=1, event_id="evt_old"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_paid)

    def test_known_plans_only_and_api_tiers(self):
        for index, plan in enumerate(["pro_annual", "api", "api_pro", "export", "unknown"]):
            on_subscription_active(self.event({"id": "sub_test", "status": "active", "metadata": {
                "user_id": str(self.user.pk), "plan_key": plan,
            }}, seconds=index, event_id=f"evt_{index}"))
            self.user.refresh_from_db()
            self.assertEqual(self.user.is_paid, plan in {"pro_annual", "api", "api_pro"})
            self.assertEqual(self.user.has_api_access, plan in {"api", "api_pro"})

    def test_invoice_failure_cannot_override_recovered_subscription(self):
        on_subscription_active(self.subscription("active"))
        on_payment_failed(self.event({"status": "past_due"}))
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_paid)

    def test_export_requires_paid_status_and_grants_once_per_intent(self):
        obj = {"mode": "payment", "payment_intent": "pi_export", "payment_status": "unpaid",
               "metadata": {"user_id": str(self.user.pk), "plan_key": "export"}}
        on_checkout_completed(self.event(obj))
        self.assertFalse(ExportToken.objects.exists())
        obj["payment_status"] = "paid"
        on_checkout_completed(self.event(obj))
        token = ExportToken.objects.get()
        token.consume()
        # Both duplicate deliveries and the async-success event share this key.
        on_checkout_completed(self.event(obj, event_id="evt_async"))
        self.assertEqual(ExportToken.objects.count(), 1)
        self.assertEqual(ExportToken.objects.filter(used_at__isnull=True).count(), 0)

    def test_paid_export_without_payment_identity_does_not_grant(self):
        with self.assertRaises(ValueError):
            on_checkout_completed(self.event({"mode": "payment", "payment_status": "paid",
                "metadata": {"user_id": str(self.user.pk), "plan_key": "export"}}))
        self.assertFalse(ExportToken.objects.exists())

    def test_payment_intent_constraint(self):
        ExportToken.objects.create(user=self.user, stripe_payment_intent="pi_one")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExportToken.objects.create(user=self.user, stripe_payment_intent="pi_one")


    def test_test_mode_signal_cannot_grant_live_entitlements(self):
        with override_settings(STRIPE_LIVE_MODE=True):
            on_subscription_active(self.subscription('active'))
            on_checkout_completed(self.event({'mode': 'payment', 'payment_status': 'paid',
                'payment_intent': 'pi_wrong_mode',
                'metadata': {'user_id': str(self.user.pk), 'plan_key': 'export'}}))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_paid)
        self.assertFalse(ExportToken.objects.exists())

    def test_same_second_plan_change_does_not_restore_api_access(self):
        on_subscription_active(self.event({'id': 'sub_test', 'status': 'active',
            'metadata': {'user_id': str(self.user.pk), 'plan_key': 'pro'}}, event_id='evt_pro'))
        with patch('subscriptions.signals.stripe.Subscription.retrieve', return_value={
            'id': 'sub_test', 'status': 'active',
            'metadata': {'user_id': str(self.user.pk), 'plan_key': 'pro'},
        }) as retrieve:
            on_subscription_active(self.event({'id': 'sub_test', 'status': 'active',
                'metadata': {'user_id': str(self.user.pk), 'plan_key': 'api'}}, event_id='evt_old_api'))
        retrieve.assert_called_once()
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_api_access)
        self.assertTrue(self.user.is_paid)
