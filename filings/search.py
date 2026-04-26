from django.contrib.postgres.search import TrigramSimilarity
from django.db import connection
from django.db.models import Q, QuerySet

from .models import Filing, RelatedPerson

SORT_CHOICES = {
    "newest": ("-filing_date", "-id"),
    "oldest": ("filing_date", "id"),
    "largest": ("-total_offering_amount", "-filing_date"),
    "smallest": ("total_offering_amount", "-filing_date"),
}


def _is_postgres() -> bool:
    return connection.vendor == "postgresql"


def build_filing_query(params) -> QuerySet:
    qs = Filing.objects.select_related("issuer").all()

    q = (params.get("q") or "").strip()
    has_text_search = bool(q)
    if q:
        if _is_postgres():
            qs = qs.annotate(sim=TrigramSimilarity("issuer__name", q)).filter(
                Q(issuer__name__icontains=q) | Q(sim__gt=0.15)
            )
        else:
            qs = qs.filter(issuer__name__icontains=q)

    states = [s.strip().upper() for s in params.getlist("state") if s.strip()] \
        if hasattr(params, "getlist") else [s.strip().upper() for s in [params.get("state", "")] if s.strip()]
    if states:
        qs = qs.filter(issuer__state__in=states)

    industries = [i.strip() for i in params.getlist("industry") if i.strip()] \
        if hasattr(params, "getlist") else [i.strip() for i in [params.get("industry", "")] if i.strip()]
    industry_mode = (params.get("industry_mode") or "include").lower()
    if industries:
        if industry_mode == "exclude":
            qs = qs.exclude(industry_group__in=industries)
        else:
            qs = qs.filter(industry_group__in=industries)

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
    if sort == "relevance" and has_text_search and _is_postgres():
        qs = qs.order_by("-sim", "-filing_date")
    elif sort in SORT_CHOICES:
        qs = qs.order_by(*SORT_CHOICES[sort])
    else:
        qs = qs.order_by(*SORT_CHOICES["newest"])
    return qs


def search_persons(q: str, limit: int = 20) -> list[dict]:
    """Top-N distinct people whose name matches q (trigram + icontains)."""
    if not q or len(q.strip()) < 2:
        return []
    q = q.strip()
    if _is_postgres():
        qs = (
            RelatedPerson.objects.annotate(sim=TrigramSimilarity("name", q))
            .filter(Q(name__icontains=q) | Q(sim__gt=0.2))
            .values("name_slug", "name")
            .order_by("name_slug")
            .distinct()
        )
    else:
        qs = (
            RelatedPerson.objects.filter(name__icontains=q)
            .values("name_slug", "name")
            .order_by("name_slug")
            .distinct()
        )
    # Rank by aggregate similarity of the best-matching row for each slug.
    seen: dict[str, dict] = {}
    for row in qs[:limit * 3]:
        slug = row["name_slug"]
        if slug and slug not in seen:
            seen[slug] = row
        if len(seen) >= limit:
            break
    return list(seen.values())


def active_filters(params) -> list[dict]:
    """Return a list of human-readable {label, remove_key} for filter chips."""
    chips: list[dict] = []
    single_mapping = [
        ("q", "search"),
        ("date_from", "from"),
        ("date_to", "to"),
        ("min_amount", "min"),
        ("max_amount", "max"),
    ]
    for key, prefix in single_mapping:
        val = (params.get(key) or "").strip()
        if not val:
            continue
        chips.append({"label": f"{prefix}: {val}", "remove_key": key})
    industry_mode = (params.get("industry_mode") or "include").lower()
    industry_prefix = "exclude industry" if industry_mode == "exclude" else "industry"
    multi_mapping = [("state", "state"), ("industry", industry_prefix)]
    for key, prefix in multi_mapping:
        if hasattr(params, "getlist"):
            vals = [v for v in params.getlist(key) if v.strip()]
        else:
            v = (params.get(key) or "").strip()
            vals = [v] if v else []
        for v in vals:
            chips.append({"label": f"{prefix}: {v}", "remove_key": key})
    return chips
