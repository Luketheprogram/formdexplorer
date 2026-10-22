from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404

from filings.models import Filing, Issuer
from filings.search import build_filing_query
from filings.search_params import SearchValidationError

from .auth import api_key_required
from .serializers import filing_dict, issuer_dict

MAX_LIMIT = 200


@api_key_required
def filings_list(request):
    try:
        limit = max(1, min(int(request.GET.get("limit", "50")), MAX_LIMIT))
        offset = max(int(request.GET.get("offset", "0")), 0)
        if offset > 9223372036854775807 - limit:
            raise ValueError
    except ValueError:
        return JsonResponse({"error": "bad_pagination"}, status=400)

    try:
        qs = build_filing_query(request.GET)
    except SearchValidationError as exc:
        return JsonResponse({"error": "invalid_filters", "fields": exc.errors}, status=400)
    total = qs.count()
    items = list(qs[offset : offset + limit])
    return JsonResponse(
        {
            "count": total,
            "limit": limit,
            "offset": offset,
            "results": [filing_dict(f) for f in items],
        }
    )


@api_key_required
def filing_detail(request, accession_number: str):
    f = get_object_or_404(
        Filing.objects.select_related("issuer").prefetch_related("related_persons"),
        accession_number=accession_number,
    )
    return JsonResponse(filing_dict(f, include_related=True))


@api_key_required
def issuer_detail(request, cik: str):
    if not cik.isdigit():
        raise Http404
    i = get_object_or_404(Issuer, cik=cik)
    recent = list(i.filings.order_by("-filing_date")[:25])
    return JsonResponse(
        {
            **issuer_dict(i),
            "recent_filings": [filing_dict(f) for f in recent],
        }
    )
