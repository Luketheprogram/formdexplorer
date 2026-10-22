"""Shared crawl policy; robots.txt deliberately permits reading noindex pages."""
from urllib.parse import urlsplit

from django.conf import settings
from django.core.paginator import InvalidPage, Paginator
from django.http import Http404, HttpResponsePermanentRedirect
from django.utils.encoding import iri_to_uri


PRIVATE_PREFIXES = (
    "/admin/", "/account/", "/login/", "/logout/", "/signup/", "/search/",
    "/saved-searches/", "/watchlist/", "/export/", "/checkout/", "/stripe/",
    "/api/", "/feed/", "/learn/newsletter/", "/person/",
)


def noindex(request):
    match = request.resolver_match
    utility = request.path.startswith(PRIVATE_PREFIXES) or (
        match and match.url_name in {
            "search", "search_partial", "issuer_watch_toggle", "issuer_enrich",
            "issuer_infer_website", "export_csv", "export_xlsx",
        }
    )
    return bool(
        not settings.SEO_INDEXING_ENABLED
        or (not settings.DEBUG and request.get_host().lower() != urlsplit(settings.SITE_URL).netloc.lower())
        or utility or getattr(request, "seo_noindex", False)
        or request.headers.get("HX-Request") == "true"
    )


def paginate(request, queryset, per_page=50):
    """Never return page one/last page with 200 for invalid pagination URLs."""
    try:
        return Paginator(queryset, per_page).page(request.GET.get("page", "1"))
    except InvalidPage as exc:
        raise Http404("Page not found") from exc


def collection_meta(request, context, page):
    if not page.paginator.count:
        request.seo_noindex = True
        context["robots"] = "noindex, follow"
    if page.number > 1:
        context["canonical_path"] += f"?page={page.number}"
        # Title/description pagination is applied once by config.metadata.
        # Retain crawlable links and a self-canonical, but focus indexing on hubs.
        request.seo_noindex = True
        context["robots"] = "noindex, follow"
    return context


class SEOMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().lower().split(":")[0]
        target = urlsplit(settings.SITE_URL)
        if (
            not settings.DEBUG and settings.SEO_INDEXING_ENABLED
            and request.method in {"GET", "HEAD"}
            and host in settings.CANONICAL_REDIRECT_HOSTS
            and host != target.hostname
            and not request.path.startswith(("/api/", "/stripe/", "/admin/"))
        ):
            return HttpResponsePermanentRedirect(settings.SITE_URL + request.get_full_path())
        response = self.get_response(request)
        if noindex(request) or response.status_code >= 400:
            response["X-Robots-Tag"] = "noindex, follow"
        return response


def canonical_url(context):
    return settings.SITE_URL + iri_to_uri(context.get("canonical_path") or context["request"].path)
