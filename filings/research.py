"""Public filing-activity summaries. Never sum amendments into fundraising totals."""
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Max, Min, Q
from django.db.models.functions import Lower, Trim
from django.utils import timezone

from .industry import NAME_TO_SLUG
from .models import Filing
from .states import US_STATES


def activity_stats(queryset):
    today = timezone.localdate()
    amendment = Q(is_amendment=True) | Q(form_type=Filing.FORM_D_A)
    return queryset.aggregate(
        total_filings=Count("id"),
        issuer_count=Count("issuer_id", distinct=True),
        amendment_count=Count("id", filter=amendment),
        original_count=Count("id", filter=~amendment),
        filings_last_year=Count("id", filter=Q(filing_date__gte=today - timedelta(days=365), filing_date__lte=today)),
        first_filed=Min("filing_date"), last_filed=Max("filing_date"),
    )


def directory_data():
    """Cache small, public aggregates, never personalized HTML or query strings.

    A 15-minute TTL works across the separately deployed ingestion process;
    signals in the web process would not invalidate the ingest worker's cache.
    """
    def build():
        qs = Filing.objects.alias(issuer_name=Trim("issuer__name")).exclude(issuer_name="").order_by()
        state_rows = {r["issuer__state"]: r for r in qs.values("issuer__state").annotate(
            filing_count=Count("id"), issuer_count=Count("issuer_id", distinct=True), latest=Max("filing_date"))}
        industry_rows = {r["key"]: r for r in qs.annotate(key=Lower("industry_group")).values("key").annotate(
            filing_count=Count("id"), issuer_count=Count("issuer_id", distinct=True), latest=Max("filing_date"))}
        return {
            "states": [dict(state_rows[code], name=name, url=f"/state/{code}/", code=code)
                       for code, name in US_STATES if code in state_rows],
            "industries": [dict(industry_rows[name.lower()], name=name, url=f"/industry/{slug}/", slug=slug)
                           for name, slug in NAME_TO_SLUG.items() if name.lower() in industry_rows],
        }
    return cache.get_or_set("research:directories:v1", build, 900)
