"""Stripe webhook handlers. dj-stripe verifies signature and persists events;
we react via djstripe_receiver signals."""

import logging
import stripe

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from djstripe import models as dj
from djstripe.event_handlers import djstripe_receiver

from accounts.models import ExportToken
from .plans import PLANS

log = logging.getLogger(__name__)
User = get_user_model()


def _user_from_metadata(event: dj.Event):
    # Also protect delivery through dj-stripe's own webhook URL.
    if event.livemode is not settings.STRIPE_LIVE_MODE:
        return None, {}
    md = (event.data.get("object", {}) or {}).get("metadata") or {}
    uid = md.get("user_id")
    if not uid:
        return None, md
    try:
        return User.objects.get(pk=uid), md
    except (User.DoesNotExist, ValueError, TypeError):
        return None, md


@djstripe_receiver(["checkout.session.completed", "checkout.session.async_payment_succeeded"])
@transaction.atomic
def on_checkout_completed(event: dj.Event, **kwargs):
    user, md = _user_from_metadata(event)
    if user is None:
        return
    user = User.objects.select_for_update().get(pk=user.pk)
    obj = event.data.get("object", {}) or {}
    customer_id = obj.get("customer")
    if customer_id and not user.stripe_customer_id:
        user.stripe_customer_id = customer_id
    plan_key = md.get("plan_key")
    mode = obj.get("mode")
    if mode == "payment" and plan_key == "export" and obj.get("payment_status") == "paid":
        payment_intent = obj.get("payment_intent")
        if not isinstance(payment_intent, str) or not payment_intent:
            raise ValueError("Paid export checkout is missing its payment intent")
        token, _ = ExportToken.objects.get_or_create(
            stripe_payment_intent=payment_intent, defaults={"user": user},
        )
        if token.user_id != user.pk:
            raise ValueError("Export payment intent is already assigned to another account")
    user.save(update_fields=["stripe_customer_id"])
    log.info("checkout.session.completed for user %s plan %s", user.id, plan_key)


@djstripe_receiver([
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.resumed",
    "customer.subscription.deleted",
    "customer.subscription.paused",
])
@transaction.atomic
def on_subscription_active(event: dj.Event, **kwargs):
    user, md = _user_from_metadata(event)
    if user is None:
        return
    user = User.objects.select_for_update().get(pk=user.pk)
    obj = event.data.get("object", {}) or {}
    status = obj.get("status", "")
    created = event.created
    subscription_id = obj.get("id")
    if not created or not subscription_id:
        raise ValueError("Subscription event is missing its timestamp or subscription ID")
    if user.subscription_event_id == event.id:
        return
    if user.subscription_event_created and created < user.subscription_event_created:
        return
    # An ended older subscription must not revoke its replacement.
    if (user.stripe_subscription_id and user.stripe_subscription_id != subscription_id
            and status not in {"active", "trialing"}):
        return
    # Different transitions can share a second, including the first successful
    # payment after an incomplete subscription. Resolve ties from Stripe rather
    # than guessing order or leaving a legitimate customer locked out.
    if created == user.subscription_event_created:
        key = settings.STRIPE_LIVE_SECRET_KEY if settings.STRIPE_LIVE_MODE else settings.STRIPE_TEST_SECRET_KEY
        current = stripe.Subscription.retrieve(subscription_id, api_key=key)
        md = current.get("metadata") or {}
        if current.get("id") != subscription_id or str(md.get("user_id")) != str(user.pk):
            raise ValueError("Subscription reconciliation returned a different account")
        status = current.get("status", "")
    user.subscription_status = status
    user.subscription_tier = User.SUBSCRIPTION_FREE
    if status in {"active", "trialing"}:
        plan = PLANS.get(md.get("plan_key"))
        if plan and plan.mode == "subscription":
            user.subscription_tier = plan.tier
    user.stripe_subscription_id = subscription_id
    user.subscription_event_created = created
    user.subscription_event_id = event.id
    user.save(update_fields=["subscription_status", "subscription_tier", "stripe_subscription_id",
                             "subscription_event_created", "subscription_event_id"])


@djstripe_receiver("invoice.payment_failed")
def on_payment_failed(event: dj.Event, **kwargs):
    # Invoice metadata is not subscription metadata, and a delayed invoice
    # event must not overwrite a recovered subscription. Subscription events
    # are the authoritative source for entitlement status.
    log.info("Invoice payment failed; subscription status is updated by subscription webhooks")
