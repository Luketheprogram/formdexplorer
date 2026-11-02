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
from config.metadata import filing_metadata, metadata

from filings.search_params import (
    SearchValidationError,
    normalize_search_params,
    validated_export,
)
from filings.exports import finish_export, xlsx_response
from filings.views import _enforce_export_gate

from .models import CrowdfundingFiling

logger = logging.getLogger(__name__)

EXPORT_ROW_LIMIT = 5000


def _is_postgres() -> bool:
    return connection.vendor == "postgresql"


def _build_qs(params):
    params = normalize_search_params(params)
    qs = CrowdfundingFiling.objects.select_related("issuer").defer("raw_xml").all()
    q = (params.get("q") or "").strip()
    identifier = re.fullmatch(r"(?:CIK[: ]*)?([0-9]{1,10})", q, re.I)
    if identifier:
        value = identifier.group(1)
        qs = qs.filter(
            issuer__cik__in={value.lstrip("0") or "0", value.zfill(10)}
        ).order_by("-filing_date", "-id")
    elif q:
        if _is_postgres():
            qs = (
                qs.annotate(sim=TrigramSimilarity("issuer__name", q))
                .filter(
                    Q(issuer__name__icontains=q)
                    | Q(intermediary_name__icontains=q)
                    | Q(sim__gt=0.15)
                )
                .order_by("-sim", "-filing_date", "-id")
            )
        else:
            qs = qs.filter(
                Q(issuer__name__icontains=q) | Q(intermediary_name__icontains=q)
            ).order_by("-filing_date", "-id")
    else:
        qs = qs.order_by("-filing_date", "-id")

    intermediary = (params.get("intermediary") or "").strip()
    if intermediary:
        qs = qs.filter(intermediary_name__icontains=intermediary)

    state = (params.get("state") or "").strip().upper()
    if state:
        qs = qs.filter(issuer__state=state)

    form_types = (
        [f for f in params.getlist("form_type") if f]
        if hasattr(params, "getlist")
        else []
    )
    if form_types:
        qs = qs.filter(form_type__in=form_types)

    min_amt = params.get("min_amount")
    if min_amt:
        try:
            qs = qs.filter(maximum_offering_amount__gte=int(min_amt))
        except ValueError:
            pass
    if params.get("date_from"):
        qs = qs.filter(filing_date__gte=params["date_from"])
    if params.get("date_to"):
        qs = qs.filter(filing_date__lte=params["date_to"])
    if params.get("max_amount"):
        qs = qs.filter(maximum_offering_amount__lte=int(params["max_amount"]))
    if params.get("amount_status") == "known":
        qs = qs.filter(maximum_offering_amount__gte=0)
    elif params.get("amount_status") == "missing":
        qs = qs.filter(
            Q(maximum_offering_amount__isnull=True) | Q(maximum_offering_amount__lt=0)
        )
    return qs


def search(request):
    q = (request.GET.get("q") or "").strip()
    errors = {}
    try:
        qs = _build_qs(request.GET)
    except SearchValidationError as exc:
        errors = exc.errors
        qs = CrowdfundingFiling.objects.none()
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page"))
    ctx = {
        "search_errors": errors,
        "q": q,
        "page_obj": page,
        "total": qs.count(),
        **metadata(
            "Crowdfunding Filings — SEC Form C Search",
            "Search SEC Form C crowdfunding filings, amendments, and reports. Explore issuers, "
            "funding portals, reported offering targets, and available financial data.",
            page=page,
        ),
        "canonical_path": "/cf/",
    }
    ctx.update(page_context(request, qs))
    return render(request, "crowdfunding/search.html", ctx)


def search_partial(request):
    errors = {}
    try:
        qs = _build_qs(request.GET)
    except SearchValidationError as exc:
        errors = exc.errors
        qs = CrowdfundingFiling.objects.none()
    context = dict(
        page_context(request, qs), q=request.GET.get("q", ""), search_errors=errors
    )
    return search_response(
        request, render(request, "crowdfunding/_partials/results.html", context)
    )


def detail(request, accession_number: str):
    filing = get_object_or_404(
        CrowdfundingFiling.objects.select_related("issuer").defer("raw_xml"),
        accession_number=accession_number,
    )
    # Cross-links: same issuer's Form D filings; matched advisers
    form_d_filings = filing.issuer.filings.defer("raw_xml").order_by(
        "-filing_date", "-id"
    )[:10]
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
        **filing_metadata(
            filing,
            "View the Reg CF filing record, available disclosures, and SEC EDGAR source.",
        ),
        "canonical_path": f"/cf/{filing.accession_number}/",
    }
    return render(request, "crowdfunding/detail.html", ctx)


@login_required
@validated_export
def export_xlsx(request):
    """Form C xlsx export — same filters as /cf/ search."""
    try:
        ok, token, resp = _enforce_export_gate(request)
        if not ok:
            return resp

        qs = _build_qs(request.GET)[:EXPORT_ROW_LIMIT]
        headers = [
            "Issuer",
            "Website",
            "Filing date",
            "Target offering ($)",
            "Maximum offering ($)",
            "Security type",
            "Intermediary (funding portal)",
        ]
        rows = []
        for f in qs:
            rows.append(
                [
                    f.issuer.name,
                    f.issuer.website or "",
                    f.filing_date.isoformat() if f.filing_date else "",
                    f.target_offering_amount,
                    f.maximum_offering_amount,
                    f.security_type or "",
                    f.intermediary_name or "",
                ]
            )
        filename = f"form-c-filings-{timezone.now().date().isoformat()}.xlsx"
        response = xlsx_response(filename, rows, headers)
        return finish_export(request, response, token)
    except SearchValidationError:
        raise
    except Exception:
        logger.exception(
            "crowdfunding.export_xlsx failed for user=%s GET=%s",
            request.user,
            request.GET.urlencode(),
        )
        raise
