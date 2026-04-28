from django.contrib.postgres.search import TrigramSimilarity
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from .models import CrowdfundingFiling


def _is_postgres() -> bool:
    return connection.vendor == "postgresql"


def _build_qs(params):
    qs = CrowdfundingFiling.objects.select_related("issuer").all()
    q = (params.get("q") or "").strip()
    if q:
        if _is_postgres():
            qs = qs.annotate(sim=TrigramSimilarity("issuer__name", q)).filter(
                Q(issuer__name__icontains=q) | Q(intermediary_name__icontains=q) | Q(sim__gt=0.15)
            ).order_by("-sim", "-filing_date")
        else:
            qs = qs.filter(Q(issuer__name__icontains=q) | Q(intermediary_name__icontains=q)).order_by("-filing_date")
    else:
        qs = qs.order_by("-filing_date", "-id")

    intermediary = (params.get("intermediary") or "").strip()
    if intermediary:
        qs = qs.filter(intermediary_name__icontains=intermediary)

    state = (params.get("state") or "").strip().upper()
    if state:
        qs = qs.filter(issuer__state=state)

    form_types = [f for f in params.getlist("form_type") if f] if hasattr(params, "getlist") else []
    if form_types:
        qs = qs.filter(form_type__in=form_types)

    min_amt = params.get("min_amount")
    if min_amt:
        try:
            qs = qs.filter(maximum_offering_amount__gte=int(min_amt))
        except ValueError:
            pass
    return qs


def search(request):
    q = (request.GET.get("q") or "").strip()
    qs = _build_qs(request.GET)
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page"))
    ctx = {
        "q": q,
        "page_obj": page,
        "total": qs.count(),
        "page_title": "Form C Search — Form D Explorer",
        "meta_description": (
            "Search SEC Form C / Reg CF crowdfunding filings. Issuer, intermediary "
            "(Republic, WeFunder, StartEngine, etc.), offering amount, financials."
        ),
        "canonical_path": "/cf/",
    }
    return render(request, "crowdfunding/search.html", ctx)


def search_partial(request):
    qs = _build_qs(request.GET)
    return render(
        request,
        "crowdfunding/_partials/results.html",
        {"results": qs[:50], "total": qs.count(), "q": request.GET.get("q", "")},
    )


def detail(request, accession_number: str):
    filing = get_object_or_404(
        CrowdfundingFiling.objects.select_related("issuer"),
        accession_number=accession_number,
    )
    # Cross-links: same issuer's Form D filings; matched advisers
    form_d_filings = filing.issuer.filings.order_by("-filing_date")[:10]
    likely_advisers = []
    try:
        from advisers.matching import find_matching_advisers
        likely_advisers = find_matching_advisers(filing.issuer, limit=4)
    except Exception:
        likely_advisers = []
    ctx = {
        "filing": filing,
        "form_d_filings": list(form_d_filings),
        "likely_advisers": likely_advisers,
        "page_title": (
            f"Form {filing.form_type} — {filing.issuer.name} ({filing.filing_date}) | Form D Explorer"
        ),
        "meta_description": (
            f"{filing.issuer.name} filed Form {filing.form_type} on {filing.filing_date}. "
            f"Reg CF crowdfunding offering details, intermediary, and financials."
        ),
        "canonical_path": f"/cf/{filing.accession_number}/",
    }
    return render(request, "crowdfunding/detail.html", ctx)
