from django.conf import settings
from .seo import noindex


def site_meta(request):
    return {
        "SITE_NAME": "Form D Explorer",
        "SITE_URL": settings.SITE_URL,
        "GOOGLE_SITE_VERIFICATION": settings.GOOGLE_SITE_VERIFICATION,
        "robots": "noindex, follow" if noindex(request) else "",
        "DEFAULT_META_DESCRIPTION": (
            "Search SEC Form D filings. Issuer lookup, offering details, "
            "industry and state breakdowns. Fast, clean, free."
        ),
    }
