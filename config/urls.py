from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView

from filings.sitemaps import SITEMAPS

urlpatterns = [
    path("admin/", admin.site.urls),
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
