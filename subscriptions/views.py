import logging
import uuid

import stripe
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse

from .plans import PLANS, price_id_for

log = logging.getLogger(__name__)


def _stripe_api_key() -> str:
    return settings.STRIPE_LIVE_SECRET_KEY if settings.STRIPE_LIVE_MODE else settings.STRIPE_TEST_SECRET_KEY


def pricing(request):
    ctx = {
        "plans": [p for p in PLANS.values()],
        "page_title": "Pricing — Form D Explorer",
        "meta_description": "Pro, one-time export, and API pricing for Form D Explorer.",
        "canonical_path": "/pricing/",
    }
    return render(request, "subscriptions/pricing.html", ctx)


@login_required
def checkout(request, plan_key: str):
    plan = PLANS.get(plan_key)
    if plan is None or plan.phase > 2:
        raise Http404
    price_id = price_id_for(plan)
    if not price_id:
        return HttpResponseBadRequest("Plan not yet configured.")

    stripe.api_key = _stripe_api_key()
    success_url = request.build_absolute_uri(reverse("subscriptions:checkout_success")) + "?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = request.build_absolute_uri(reverse("subscriptions:checkout_cancel"))

    client_ref = str(uuid.uuid4())
    metadata = {"user_id": str(request.user.id), "plan_key": plan.key, "client_ref": client_ref}

    session_kwargs = dict(
        mode=plan.mode,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        customer_email=request.user.email if not request.user.stripe_customer_id else None,
        customer=request.user.stripe_customer_id or None,
        client_reference_id=client_ref,
        metadata=metadata,
    )
    if plan.mode == "subscription":
        session_kwargs["subscription_data"] = {"metadata": metadata}
    else:
        session_kwargs["payment_intent_data"] = {"metadata": metadata}

    session = stripe.checkout.Session.create(**{k: v for k, v in session_kwargs.items() if v is not None})
    return redirect(session.url, permanent=False)


@login_required
def checkout_success(request):
    ctx = {
        "page_title": "Payment successful — Form D Explorer",
        "meta_description": "Your purchase was successful.",
        "robots": "noindex",
    }
    return render(request, "subscriptions/checkout_success.html", ctx)


@login_required
def checkout_cancel(request):
    ctx = {
        "page_title": "Checkout canceled — Form D Explorer",
        "meta_description": "Your checkout was canceled.",
        "robots": "noindex",
    }
    return render(request, "subscriptions/checkout_cancel.html", ctx)
