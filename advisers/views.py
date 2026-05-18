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
from filings.models import Filing, Issuer
from filings.views import _enforce_export_gate

from .matching import find_matching_issuers
from .models import Adviser

logger = logging.getLogger(__name__)

EXPORT_ROW_LIMIT = 5000


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


@login_required
def export_xlsx(request):
    """Adviser xlsx export — same query as /adv/?q=..."""
    try:
        ok, token, resp = _enforce_export_gate(request)
        if not ok:
            return resp

        q = (request.GET.get("q") or "").strip()
        qs = _build_queryset(q)[:EXPORT_ROW_LIMIT]
        headers = [
            "Firm name", "Last filed", "Discretionary AUM ($)", "Regulatory AUM ($)",
            "State", "CRD",
        ]
        rows = []
        for a in qs:
            rows.append([
                a.name,
                a.last_filed_at.isoformat() if a.last_filed_at else "",
                a.discretionary_aum,
                a.regulatory_aum,
                a.state or "",
                a.crd,
            ])
        filename = f"form-adv-firms-{timezone.now().date().isoformat()}.xlsx"
        response = xlsx_response(filename, rows, headers)
        if token is not None:
            token.consume()
        return response
    except Exception:
        logger.exception("advisers.export_xlsx failed for user=%s GET=%s", request.user, request.GET.urlencode())
        raise
