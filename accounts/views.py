from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from api.models import ApiKey

from .forms import SignupForm


def signup(request):
    if request.user.is_authenticated:
        return redirect("accounts:account")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("accounts:account")
    return render(
        request,
        "accounts/signup.html",
        {
            "form": form,
            "page_title": "Sign up — Form D Explorer",
            "meta_description": "Create a free Form D Explorer account.",
            "robots": "noindex",
        },
    )


@login_required
def account(request):
    return render(
        request,
        "accounts/account.html",
        {
            "page_title": "Account — Form D Explorer",
            "robots": "noindex",
            "export_tokens_unused": request.user.export_tokens.filter(used_at__isnull=True).count(),
        },
    )


@login_required
def api_keys(request):
    keys = request.user.api_keys.filter(revoked_at__isnull=True)
    new_key = request.session.pop("_new_api_key", None)
    return render(
        request,
        "accounts/api_keys.html",
        {
            "keys": keys,
            "new_key": new_key,
            "page_title": "API keys — Form D Explorer",
            "robots": "noindex",
        },
    )


@login_required
def api_key_create(request):
    if request.method != "POST":
        return redirect("accounts:api_keys")
    if request.user.subscription_tier != request.user.SUBSCRIPTION_API:
        messages.info(request, "API access requires the API subscription.")
        return redirect("subscriptions:pricing")
    name = (request.POST.get("name") or "Default").strip()[:80] or "Default"
    _, raw = ApiKey.generate(request.user, name=name)
    request.session["_new_api_key"] = raw
    return redirect("accounts:api_keys")


@login_required
def api_key_revoke(request, pk: int):
    key = get_object_or_404(ApiKey, pk=pk, user=request.user)
    if request.method == "POST":
        key.revoke()
    return redirect("accounts:api_keys")
