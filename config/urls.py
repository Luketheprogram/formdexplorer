from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView

from filings.sitemaps import SITEMAPS

_UPDATED = "2026-04-24"

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "privacy/",
        TemplateView.as_view(
            template_name="legal/privacy.html",
            extra_context={"page_title": "Privacy — Form D Explorer", "canonical_path": "/privacy/", "updated": _UPDATED},
        ),
        name="privacy",
    ),
    path(
        "terms/",
        TemplateView.as_view(
            template_name="legal/terms.html",
            extra_context={"page_title": "Terms of Service — Form D Explorer", "canonical_path": "/terms/", "updated": _UPDATED},
        ),
        name="terms",
    ),
    path("learn/", include("content.urls")),
    path("api/", include("api.urls")),
    path("", include("accounts.urls")),
    path("", include("subscriptions.urls")),
    path("stripe/", include("djstripe.urls", namespace="djstripe")),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    path(
        "robots.txt",
        TemplateView.as_view(template_name="robots.txt", content_type="text/plain"),
        name="robots",
    ),
    path("", include("filings.urls")),
]
