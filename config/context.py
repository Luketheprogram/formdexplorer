from django.conf import settings


def site_meta(request):
    return {
        "SITE_NAME": "Form D Explorer",
        "SITE_URL": settings.SITE_URL,
        "DEFAULT_META_DESCRIPTION": (
            "Search SEC Form D filings. Issuer lookup, offering details, "
            "industry and state breakdowns. Fast, clean, free."
        ),
    }
