from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from content.models import Article

from .industry import NAME_TO_SLUG
from .models import Filing, Issuer


class StaticSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.7

    def items(self):
        return ["filings:home", "filings:recent", "content:article_list"]

    def location(self, item):
        return reverse(item)


class IssuerSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8
    limit = 5000

    def items(self):
        return Issuer.objects.all().order_by("id")

    def location(self, obj: Issuer) -> str:
        return f"/issuer/{obj.url_slug}/"

    def lastmod(self, obj: Issuer):
        return obj.updated_at


class FilingSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5
    limit = 5000

    def items(self):
        return Filing.objects.all().order_by("-filing_date", "-id")

    def location(self, obj: Filing) -> str:
        return f"/filing/{obj.accession_number}/"

    def lastmod(self, obj: Filing):
        return obj.updated_at


class IndustrySitemap(Sitemap):
    changefreq = "daily"
    priority = 0.6

    def items(self):
        return list(NAME_TO_SLUG.values())

    def location(self, slug: str) -> str:
        return f"/industry/{slug}/"


class ArticleSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return Article.objects.exclude(published_at__isnull=True)

    def location(self, obj: Article) -> str:
        return f"/learn/{obj.slug}/"

    def lastmod(self, obj: Article):
        return obj.updated_at


SITEMAPS = {
    "static": StaticSitemap,
    "issuers": IssuerSitemap,
    "filings": FilingSitemap,
    "industries": IndustrySitemap,
    "articles": ArticleSitemap,
}
