import logging

from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import TrigramSimilarity
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from filings.exports import xlsx_response
from filings.views import _enforce_export_gate

from .models import Form1AFiling

logger = logging.getLogger(__name__)

EXPORT_ROW_LIMIT = 5000


def _is_postgres() -> bool:
    return connection.vendor == "postgresql"


def _build_qs(params):
    qs = Form1AFiling.objects.select_related("issuer").all()
    q = (params.get("q") or "").strip()
    if q:
        if _is_postgres():
            qs = qs.annotate(sim=TrigramSimilarity("issuer__name", q)).filter(
                Q(issuer__name__icontains=q) | Q(sim__gt=0.15)
            ).order_by("-sim", "-filing_date")
        else:
            qs = qs.filter(issuer__name__icontains=q).order_by("-filing_date")
    else:
        qs = qs.order_by("-filing_date", "-id")

    state = (params.get("state") or "").strip().upper()
    if state:
        qs = qs.filter(issuer__state=state)

    tier = (params.get("tier") or "").strip()
    if tier:
        qs = qs.filter(tier__icontains=tier)

    min_amt = params.get("min_amount")
    if min_amt:
        try:
            qs = qs.filter(total_offering_amount__gte=int(min_amt))
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
        "page_title": "Form 1-A Search — Form D Explorer",
        "meta_description": (
            "Search SEC Reg A+ filings (Form 1-A / 1-K / 1-U / 1-Z). Tier 1 vs "
            "Tier 2, offering size, audited financials, and cross-links to Form D."
        ),
        "canonical_path": "/1a/",
    }
    return render(request, "rega/search.html", ctx)


def search_partial(request):
    qs = _build_qs(request.GET)
    return render(
        request,
        "rega/_partials/results.html",
        {"results": qs[:50], "total": qs.count(), "q": request.GET.get("q", "")},
    )


def detail(request, accession_number: str):
    filing = get_object_or_404(
        Form1AFiling.objects.select_related("issuer"),
        accession_number=accession_number,
    )
    form_d_filings = list(filing.issuer.filings.order_by("-filing_date")[:10])
    crowdfunding_filings: list = []
    try:
        crowdfunding_filings = list(
            filing.issuer.crowdfunding_filings.order_by("-filing_date")[:5]
        )
    except Exception:
        crowdfunding_filings = []
    likely_advisers = []
    try:
        from advisers.matching import find_matching_advisers
        likely_advisers = find_matching_advisers(filing.issuer, limit=4)
    except Exception:
        likely_advisers = []
    ctx = {
        "filing": filing,
        "form_d_filings": form_d_filings,
        "crowdfunding_filings": crowdfunding_filings,
        "likely_advisers": likely_advisers,
        "page_title": (
            f"Form {filing.form_type} — {filing.issuer.name} ({filing.filing_date}) | Form D Explorer"
        ),
        "meta_description": (
            f"{filing.issuer.name} filed Form {filing.form_type} on {filing.filing_date}. "
            f"Reg A+ offering details, tier, and financials."
        ),
        "canonical_path": f"/1a/{filing.accession_number}/",
    }
    return render(request, "rega/detail.html", ctx)


@login_required
def export_xlsx(request):
    """Form 1-A xlsx export — same filters as /1a/ search."""
    try:
        ok, token, resp = _enforce_export_gate(request)
        if not ok:
            return resp

        qs = _build_qs(request.GET)[:EXPORT_ROW_LIMIT]
        headers = [
            "Issuer", "Filing date", "Amount sold ($)", "Total offering ($)",
            "Tier", "Security type",
        ]
        rows = []
        for f in qs:
            rows.append([
                f.issuer.name,
                f.filing_date.isoformat() if f.filing_date else "",
                f.total_amount_sold,
                f.total_offering_amount,
                f.tier or "",
                f.security_type or "",
            ])
        filename = f"form-1a-filings-{timezone.now().date().isoformat()}.xlsx"
        response = xlsx_response(filename, rows, headers)
        if token is not None:
            token.consume()
        return response
    except Exception:
        logger.exception("rega.export_xlsx failed for user=%s GET=%s", request.user, request.GET.urlencode())
        raise
