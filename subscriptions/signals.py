"""Stripe webhook handlers. dj-stripe verifies signature and persists events;
we react via djstripe_receiver signals."""

import logging

from django.contrib.auth import get_user_model
from djstripe import models as dj
from djstripe.event_handlers import djstripe_receiver

from accounts.models import ExportToken

log = logging.getLogger(__name__)
User = get_user_model()


def _user_from_metadata(event: dj.Event):
    md = (event.data.get("object", {}) or {}).get("metadata") or {}
    uid = md.get("user_id")
    if not uid:
        return None, md
    try:
        return User.objects.get(pk=uid), md
    except User.DoesNotExist:
        return None, md


@djstripe_receiver("checkout.session.completed")
def on_checkout_completed(event: dj.Event, **kwargs):
    user, md = _user_from_metadata(event)
    if user is None:
        return
    obj = event.data.get("object", {}) or {}
    customer_id = obj.get("customer")
    if customer_id and not user.stripe_customer_id:
        user.stripe_customer_id = customer_id
    plan_key = md.get("plan_key")
    mode = obj.get("mode")
    if mode == "payment" and plan_key == "export":
        ExportToken.objects.create(user=user, stripe_payment_intent=obj.get("payment_intent") or "")
    user.save(update_fields=["stripe_customer_id"])
    log.info("checkout.session.completed for user %s plan %s", user.id, plan_key)


@djstripe_receiver([
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.resumed",
])
def on_subscription_active(event: dj.Event, **kwargs):
    user, md = _user_from_metadata(event)
    if user is None:
        return
    obj = event.data.get("object", {}) or {}
    status = obj.get("status", "")
    user.subscription_status = status
    if status in {"active", "trialing"}:
        tier = md.get("plan_key")
        if tier == "api":
            user.subscription_tier = User.SUBSCRIPTION_API
        else:
            user.subscription_tier = User.SUBSCRIPTION_PRO
    user.save(update_fields=["subscription_status", "subscription_tier"])


@djstripe_receiver([
    "customer.subscription.deleted",
    "customer.subscription.paused",
])
def on_subscription_inactive(event: dj.Event, **kwargs):
    user, _ = _user_from_metadata(event)
    if user is None:
        return
    user.subscription_status = (event.data.get("object", {}) or {}).get("status", "canceled")
    user.subscription_tier = User.SUBSCRIPTION_FREE
    user.save(update_fields=["subscription_status", "subscription_tier"])


@djstripe_receiver("invoice.payment_failed")
def on_payment_failed(event: dj.Event, **kwargs):
    user, _ = _user_from_metadata(event)
    if user is None:
        return
    user.subscription_status = "past_due"
    user.save(update_fields=["subscription_status"])
