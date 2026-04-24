import math

from django.contrib.sitemaps import Sitemap
from django.db.models import Count
from django.urls import reverse

from content.models import Article

from .industry import NAME_TO_SLUG
from .models import Filing, Issuer

PER_PAGE = 50  # keep in sync with industry/state list views


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
    """Every industry page, paginated — each page as its own URL."""

    changefreq = "daily"
    priority = 0.6
    limit = 5000

    def items(self):
        counts = {
            row["industry_group"]: row["n"]
            for row in Filing.objects.exclude(industry_group="")
            .values("industry_group")
            .annotate(n=Count("id"))
        }
        urls: list[str] = []
        for name, slug in NAME_TO_SLUG.items():
            pages = max(1, math.ceil(counts.get(name, 1) / PER_PAGE))
            urls.append(f"/industry/{slug}/")
            for page in range(2, pages + 1):
                urls.append(f"/industry/{slug}/?page={page}")
        return urls

    def location(self, url: str) -> str:
        return url


class StateSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.6
    limit = 5000

    def items(self):
        rows = (
            Issuer.objects.exclude(state="")
            .values("state")
            .annotate(n=Count("filings"))
        )
        urls: list[str] = []
        for row in rows:
            state = row["state"].upper()
            pages = max(1, math.ceil(row["n"] / PER_PAGE))
            urls.append(f"/state/{state}/")
            for page in range(2, pages + 1):
                urls.append(f"/state/{state}/?page={page}")
        return urls

    def location(self, url: str) -> str:
        return url


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
    "states": StateSitemap,
    "articles": ArticleSitemap,
}
