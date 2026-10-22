from django.conf import settings
from .metadata import DEFAULT_DESCRIPTION, DEFAULT_TITLE, SITE_NAME
from .seo import noindex


def site_meta(request):
    return {
        "SITE_NAME": SITE_NAME,
        "SITE_URL": settings.SITE_URL,
        "DEFAULT_PAGE_TITLE": DEFAULT_TITLE,
        "DEFAULT_META_DESCRIPTION": DEFAULT_DESCRIPTION,
        "GOOGLE_SITE_VERIFICATION": settings.GOOGLE_SITE_VERIFICATION,
        "robots": "noindex, follow" if noindex(request) else "",
    }
