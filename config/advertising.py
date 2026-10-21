"""Explicit, fail-closed advertising configuration; no database or network I/O."""
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.http import require_safe


def publisher_id():
    value = settings.ADSENSE_CLIENT_ID
    return value if re.fullmatch(r"ca-pub-[0-9]{16}", value) else ""


def cmp_url():
    """Only accept the Google tag URL copied from this publisher's account."""
    value = settings.ADSENSE_CMP_SCRIPT_URL
    try:
        url = urlsplit(value)
        valid = (
            publisher_id()
            and url.scheme == "https"
            and url.netloc == "fundingchoicesmessages.google.com"
            and url.path == f"/i/{publisher_id()[3:]}"
            and not url.fragment
        )
        return value if valid else ""
    except ValueError:
        return ""


def context(request):
    client = publisher_id()
    ready = bool(settings.ADSENSE_ENABLED and settings.ADSENSE_CMP_READY and client and cmp_url())
    user = getattr(request, "user", None)
    eligible = not (user and user.is_authenticated and (user.is_paid or user.is_staff))
    return {
        "adsense_client": client,
        "advertising_ready": ready,
        "advertising_eligible": ready and eligible,
    }


def placement(request, name):
    """Called only by the two editorial views, never by utility/HTMX views."""
    slot = getattr(settings, f"ADSENSE_{name.upper()}_SLOT_ID", "")
    if not context(request)["advertising_eligible"] or not re.fullmatch(r"[0-9]{10}", slot):
        return {}
    return {"ad_slot": slot, "ad_config": {"client": publisher_id(), "cmpUrl": cmp_url()}}


@require_safe
def ads_txt(request):
    client = publisher_id()
    if not client:
        return HttpResponse("# Advertising is not configured.\n", status=404, content_type="text/plain")
    return HttpResponse(
        f"google.com, {client[3:]}, DIRECT, f08c47fec0942fa0\n",
        content_type="text/plain",
    )
