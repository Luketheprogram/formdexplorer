"""Bounded, canonical sitemap sections. No searches, empty hubs or pagination."""
from types import SimpleNamespace
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import sitemap, x_robots_tag
from django.db.models import Exists, OuterRef
from django.db.models.functions import Lower, Trim
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import cache_page

from content.models import Article
from .industry import NAME_TO_SLUG
from .models import Filing, Issuer
from .research import directory_data


class CanonicalSitemap(Sitemap):
    limit = 5000

    def get_urls(self, page=1, site=None, protocol=None):
        origin = urlsplit(settings.SITE_URL)
        return super().get_urls(page, SimpleNamespace(domain=origin.netloc), origin.scheme)


class StaticSitemap(CanonicalSitemap):
    def items(self):
        urls = ["/", "/recent/", "/learn/", "/learn/api/", "/pricing/", "/privacy/", "/terms/"]
        urls += [f"/{kind}/" for kind, rows in directory_data().items() if rows]
        return urls

    def location(self, item):
        return item


class IssuerSitemap(CanonicalSitemap):
    def items(self):
        return Issuer.objects.filter(
            Exists(Filing.objects.filter(issuer_id=OuterRef("pk")))
        ).alias(issuer_name=Trim("name")).exclude(issuer_name="").only("id", "name_slug", "cik").order_by("id")

    def location(self, obj):
        return f"/issuer/{obj.url_slug}/"


class FilingSitemap(CanonicalSitemap):
    def items(self):
        # Avoid loading potentially large raw XML into each sitemap response.
        return Filing.objects.alias(issuer_name=Trim("issuer__name")).exclude(issuer_name="").only("id", "accession_number").order_by("id")

    def location(self, obj):
        return f"/filing/{obj.accession_number}/"


class IndustrySitemap(CanonicalSitemap):
    def items(self):
        present = set(Filing.objects.order_by().annotate(key=Lower("industry_group")).values_list("key", flat=True).distinct())
        return [f"/industry/{slug}/" for name, slug in NAME_TO_SLUG.items() if name.lower() in present]

    def location(self, item):
        return item


class StateSitemap(CanonicalSitemap):
    def items(self):
        states = Issuer.objects.filter(
            Exists(Filing.objects.filter(issuer_id=OuterRef("pk")))
        ).exclude(state="").order_by("state").values_list("state", flat=True).distinct()
        # The state view uses uppercase SEC codes; don't advertise invalid aliases.
        return [f"/state/{state}/" for state in states if state.isalpha() and state == state.upper()]

    def location(self, item):
        return item


class ArticleSitemap(CanonicalSitemap):
    def items(self):
        return Article.objects.filter(published_at__lte=timezone.now()).alias(
            content=Trim("body")
        ).exclude(content="").exclude(slug="api").only("slug", "updated_at").order_by("id")

    def location(self, obj):
        return f"/learn/{obj.slug}/"

    def lastmod(self, obj):
        return obj.updated_at


SITEMAPS = {
    "static": StaticSitemap, "issuers": IssuerSitemap, "filings": FilingSitemap,
    "industries": IndustrySitemap, "states": StateSitemap, "articles": ArticleSitemap,
}


@cache_page(900)
@x_robots_tag
def sitemap_index(request):
    sections = []
    for name, cls in SITEMAPS.items():
        section = cls()
        if not section.paginator.count:
            continue
        url = settings.SITE_URL + reverse("sitemap_section", kwargs={"section": name})
        for page in range(1, section.paginator.num_pages + 1):
            sections.append({"location": url + (f"?p={page}" if page > 1 else "")})
    return TemplateResponse(request, "sitemap_index.xml", {"sitemaps": sections}, content_type="application/xml")


sitemap_section = cache_page(900)(sitemap)
