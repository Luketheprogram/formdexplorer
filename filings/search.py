from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Q, QuerySet

from .models import Filing

SORT_CHOICES = {
    "newest": ("-filing_date", "-id"),
    "oldest": ("filing_date", "id"),
    "largest": ("-total_offering_amount", "-filing_date"),
    "smallest": ("total_offering_amount", "-filing_date"),
}


def build_filing_query(params) -> QuerySet:
    qs = Filing.objects.select_related("issuer").all()

    q = (params.get("q") or "").strip()
    has_text_search = bool(q)
    if q:
        qs = qs.annotate(sim=TrigramSimilarity("issuer__name", q)).filter(
            Q(issuer__name__icontains=q) | Q(sim__gt=0.15)
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

    sort = params.get("sort") or ("relevance" if has_text_search else "newest")
    if sort == "relevance" and has_text_search:
        qs = qs.order_by("-sim", "-filing_date")
    elif sort in SORT_CHOICES:
        qs = qs.order_by(*SORT_CHOICES[sort])
    else:
        qs = qs.order_by(*SORT_CHOICES["newest"])
    return qs


def active_filters(params) -> list[dict]:
    """Return a list of human-readable {label, remove_key} for filter chips."""
    chips: list[dict] = []
    mapping = [
        ("q", "search"),
        ("state", "state"),
        ("industry", "industry"),
        ("date_from", "from"),
        ("date_to", "to"),
        ("min_amount", "min"),
        ("max_amount", "max"),
    ]
    for key, prefix in mapping:
        val = (params.get(key) or "").strip()
        if not val:
            continue
        label = f"{prefix}: {val}"
        chips.append({"label": label, "remove_key": key})
    return chips
