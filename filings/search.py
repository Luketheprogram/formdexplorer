from datetime import date

from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import F, Q, QuerySet

from .models import Filing


def build_filing_query(params) -> QuerySet:
    qs = Filing.objects.select_related("issuer").all()

    q = (params.get("q") or "").strip()
    if q:
        qs = (
            qs.annotate(sim=TrigramSimilarity("issuer__name", q))
            .filter(Q(issuer__name__icontains=q) | Q(sim__gt=0.15))
            .order_by("-sim", "-filing_date")
        )

    state = (params.get("state") or "").strip().upper()
    if state:
        qs = qs.filter(issuer__state=state)

    industry = (params.get("industry") or "").strip()
    if industry:
        qs = qs.filter(industry_group__iexact=industry)

    date_from = params.get("date_from")
    date_to = params.get("date_to")
    if date_from:
        qs = qs.filter(filing_date__gte=date_from)
    if date_to:
        qs = qs.filter(filing_date__lte=date_to)

    min_amt = params.get("min_amount")
    max_amt = params.get("max_amount")
    if min_amt:
        qs = qs.filter(total_offering_amount__gte=min_amt)
    if max_amt:
        qs = qs.filter(total_offering_amount__lte=max_amt)

    if not q:
        qs = qs.order_by("-filing_date", "-id")
    return qs
