from django.contrib.postgres.search import TrigramSimilarity
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from filings.models import Filing, Issuer

from .matching import find_matching_issuers
from .models import Adviser


def _is_postgres() -> bool:
    return connection.vendor == "postgresql"


def _build_queryset(q: str):
    qs = Adviser.objects.all()
    if q:
        if _is_postgres():
            qs = qs.annotate(sim=TrigramSimilarity("name", q)).filter(
                Q(name__icontains=q) | Q(sim__gt=0.15)
            ).order_by("-sim", "name")
        else:
            qs = qs.filter(name__icontains=q).order_by("name")
    else:
        qs = qs.order_by("-regulatory_aum", "name")
    return qs


def search(request):
    q = (request.GET.get("q") or "").strip()
    qs = _build_queryset(q)
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page"))
    ctx = {
        "q": q,
        "page_obj": page,
        "total": qs.count(),
        "page_title": "ADV Search — Form D Explorer",
        "meta_description": (
            "Search SEC-registered investment advisers (Form ADV). "
            "AUM, employees, registration status, and links to Form D filings."
        ),
        "canonical_path": "/adv/",
    }
    return render(request, "advisers/search.html", ctx)


def search_partial(request):
    q = (request.GET.get("q") or "").strip()
    qs = _build_queryset(q)
    return render(
        request,
        "advisers/_partials/results.html",
        {"results": qs[:50], "total": qs.count(), "q": q},
    )


def adviser_detail(request, crd: str):
    if not crd.isdigit():
        raise Http404
    adviser = get_object_or_404(Adviser, crd=crd)
    matches = find_matching_issuers(adviser, limit=12)
    matched_issuer_ids = [m["issuer"].id for m in matches]
    matched_filings: list = []
    if matched_issuer_ids:
        matched_filings = list(
            Filing.objects.filter(issuer_id__in=matched_issuer_ids)
            .select_related("issuer")
            .order_by("-filing_date")[:25]
        )
    ctx = {
        "adviser": adviser,
        "matches": matches,
        "matched_filings": matched_filings,
        "page_title": f"{adviser.name} (Form ADV) | Form D Explorer",
        "meta_description": (
            f"{adviser.name} — Form ADV registration details, AUM, address, "
            f"and any Form D filings filed under the same name."
        ),
        "canonical_path": f"/adv/{adviser.crd}/",
    }
    return render(request, "advisers/detail.html", ctx)
