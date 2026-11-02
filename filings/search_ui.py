"""Shared search navigation. Parameters stay intact through paging and HTMX."""

from datetime import timedelta
from urllib.parse import urlencode
from django.utils import timezone
from django.core.paginator import Paginator


def public_search_path(request):
    return {
        "/adv/search/partial/": "/adv/",
        "/cf/search/partial/": "/cf/",
        "/1a/search/partial/": "/1a/",
        "/search/partial/": "/search/",
    }.get(request.path, request.path)


def page_context(request, queryset, *, size=50):
    page = Paginator(queryset, size).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    path = public_search_path(request)

    def link(number):
        query = params.copy()
        if number > 1:
            query["page"] = str(number)
        return path + ("?" + query.urlencode() if query else "")

    return {
        "search_presets": (
            [
                {
                    "label": "Filed in the last 30 days",
                    "url": path
                    + "?"
                    + urlencode(
                        {"date_from": str(timezone.localdate() - timedelta(days=30))}
                    ),
                },
                {
                    "label": "Offering amount unavailable",
                    "url": path + "?amount_status=missing",
                },
                {
                    "label": "Reported offering of $1M or more",
                    "url": path + "?min_amount=1000000",
                },
            ]
            if path != "/adv/"
            else []
        ),
        "page_obj": page,
        "results": list(page.object_list),
        "total": page.paginator.count,
        "previous_page_url": (
            link(page.previous_page_number()) if page.has_previous() else ""
        ),
        "next_page_url": link(page.next_page_number()) if page.has_next() else "",
    }


def search_response(request, response):
    query = request.GET.urlencode()
    response["HX-Replace-Url"] = public_search_path(request) + (
        "?" + query if query else ""
    )
    response["Vary"] = "HX-Request"
    return response
