from filings.search_ui import page_context, search_response
import logging
import re

from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import TrigramSimilarity
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from config.metadata import metadata, short_name

from filings.exports import finish_export, xlsx_response
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
    identifier = re.fullmatch(r"(?:CRD[: ]*)?([0-9]+)|((?:801|802)-[0-9]+)", q, re.I)
    if identifier:
        value = identifier.group(1) or identifier.group(2)
        qs = qs.filter(crd__in={value, value.lstrip("0") or "0"}).order_by("crd", "pk")
    elif q:
        if _is_postgres():
            qs = (
                qs.annotate(sim=TrigramSimilarity("name", q))
                .filter(Q(name__icontains=q) | Q(sim__gt=0.15))
                .order_by("-sim", "name", "pk")
            )
        else:
            qs = qs.filter(name__icontains=q).order_by("name", "pk")
    else:
        qs = qs.order_by("-regulatory_aum", "name", "pk")
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
        **metadata(
            "Investment Adviser Search — Form ADV",
            "Search investment adviser records from Form ADV. Review reported regulatory AUM, "
            "firm details, registration status, and SEC IAPD source links.",
            page=page,
        ),
        "canonical_path": "/adv/",
    }
    ctx.update(page_context(request, qs))
    return render(request, "advisers/search.html", ctx)


def search_partial(request):
    q = (request.GET.get("q") or "").strip()
    context = dict(page_context(request, _build_queryset(q)), q=q)
    return search_response(
        request, render(request, "advisers/_partials/results.html", context)
    )


def adviser_detail(request, crd: str):
    if not re.fullmatch(r"[0-9]+|80[12]-[0-9]+", crd):
        raise Http404
    adviser = get_object_or_404(Adviser, crd=crd)
    if not adviser.has_crd:
        request.seo_noindex = True
    matches = find_matching_issuers(adviser, limit=12)
    matched_issuer_ids = [m["issuer"].id for m in matches]
    matched_filings: list = []
    if matched_issuer_ids:
        matched_filings = list(
            Filing.objects.filter(issuer_id__in=matched_issuer_ids)
            .select_related("issuer")
            .defer("raw_xml")
            .order_by("-filing_date", "-id")[:25]
        )
    ctx = {
        "adviser": adviser,
        "matches": matches,
        "matched_filings": matched_filings,
        **metadata(
            f"{short_name(adviser.name)} — Form ADV ({adviser.identifier_label} {adviser.crd})",
            f"{short_name(adviser.name)} ({adviser.identifier_label} {adviser.crd}): Form ADV firm details, "
            "reported regulatory AUM, registration status, and the SEC IAPD source.",
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
            "Firm name",
            "Website",
            "Last filed",
            "Discretionary AUM ($)",
            "Regulatory AUM ($)",
            "State",
            "CRD",
        ]
        rows = []
        for a in qs:
            rows.append(
                [
                    a.name,
                    a.website or "",
                    a.last_filed_at.isoformat() if a.last_filed_at else "",
                    a.discretionary_aum,
                    a.regulatory_aum,
                    a.state or "",
                    a.crd,
                ]
            )
        filename = f"form-adv-firms-{timezone.now().date().isoformat()}.xlsx"
        response = xlsx_response(filename, rows, headers)
        return finish_export(request, response, token)
    except Exception:
        logger.exception(
            "advisers.export_xlsx failed for user=%s GET=%s",
            request.user,
            request.GET.urlencode(),
        )
        raise
