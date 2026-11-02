"""Read-only, bounded research over stored disclosures, never fundraising totals.

A CIK identifies a filer, not an offering. Accession numbers are unique in the
schema. We compare disclosures without inventing offering-level lineage.
"""

from datetime import date
from decimal import Decimal
from hashlib import sha256

from django.core.cache import cache
from django.db.models import Count, Max, Min, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone

from .models import Filing

CACHE_SECONDS = 900
AMENDMENT = Q(is_amendment=True) | Q(form_type=Filing.FORM_D_A)


def month_offset(day, offset):
    number = day.year * 12 + day.month - 1 + offset
    year, month = divmod(number, 12)
    return date(year, month + 1, 1)


def percent(numerator, denominator):
    if not denominator:
        return None
    return (Decimal(numerator) * 100 / Decimal(denominator)).quantize(Decimal("0.1"))


def research_queryset():
    # Blank identities and future dates are not suitable analytical observations.
    from django.db.models.functions import Trim

    return (
        Filing.objects.alias(research_name=Trim("issuer__name"))
        .exclude(research_name="")
        .filter(filing_date__lte=timezone.localdate())
        .order_by()
    )


def monthly_activity(queryset, *, today=None):
    """Twelve calendar buckets, including the explicitly partial current month.

    Empty buckets mean no *stored* records, not no market activity. Calendar
    completion is never a claim of complete SEC coverage. No money is summed.
    """
    today = today or timezone.localdate()
    start = month_offset(today, -11)
    rows = (
        queryset.order_by()
        .filter(filing_date__gte=start, filing_date__lte=today)
        .annotate(month=TruncMonth("filing_date"))
        .values("month")
        .annotate(
            filings=Count("pk", distinct=True),
            issuers=Count("issuer_id", distinct=True),
            amendments=Count("pk", distinct=True, filter=AMENDMENT),
            originals=Count("pk", distinct=True, filter=~AMENDMENT),
        )
        .order_by("month")
    )
    keyed = {row["month"]: row for row in rows}
    result = []
    for offset in range(-11, 1):
        month = month_offset(today, offset)
        row = keyed.get(
            month, dict(month=month, filings=0, issuers=0, amendments=0, originals=0)
        )
        result.append(
            dict(
                row,
                partial=offset == 0,
                amendment_share=percent(row["amendments"], row["filings"]),
            )
        )
    return result


def build_report(queryset, *, today=None):
    today = today or timezone.localdate()
    qs = queryset.filter(filing_date__lte=today)
    stats = qs.aggregate(
        filings=Count("pk", distinct=True),
        issuers=Count("issuer_id", distinct=True),
        first=Min("filing_date"),
        latest=Max("filing_date"),
        imported=Max("updated_at"),
        amendments=Count("pk", distinct=True, filter=AMENDMENT),
        offering_known=Count(
            "pk", distinct=True, filter=Q(total_offering_amount__gte=0)
        ),
        sold_known=Count("pk", distinct=True, filter=Q(total_amount_sold__gte=0)),
        investors_known=Count("pk", distinct=True, filter=Q(num_investors__gte=0)),
    )
    months = monthly_activity(qs, today=today)
    maximum = max((row["filings"] for row in months), default=0)
    for row in months:
        row["bar_percent"] = percent(row["filings"], maximum) or 0
    previous, current = months[-3], months[-2]
    delta = current["filings"] - previous["filings"]
    from researchdesk.coverage import publication_days_since

    return dict(
        latest_age_publication_days=publication_days_since(stats["latest"]),
        stats=stats,
        months=months,
        previous=previous,
        current=current,
        delta=delta,
        change_percent=percent(delta, previous["filings"]),
        amendment_share=percent(stats["amendments"], stats["filings"]),
        offering_missing=stats["filings"] - stats["offering_known"],
        sold_missing=stats["filings"] - stats["sold_known"],
        investors_missing=stats["filings"] - stats["investors_known"],
        latest_age_days=(today - stats["latest"]).days if stats["latest"] else None,
        calculated_at=timezone.now(),
        today=today,
    )


def activity_report(*, state=None, industry=None):
    """Call with validated, finite category choices. Cache only public aggregates."""
    today = timezone.localdate()
    scope = (
        f"state:{state}"
        if state
        else f"industry:{industry.casefold()}" if industry else "all"
    )
    key = f"intelligence:v1:{today.isoformat()}:{sha256(scope.encode()).hexdigest()}"

    def build():
        qs = research_queryset()
        if state:
            qs = qs.filter(issuer__state=state)
        if industry:
            qs = qs.filter(industry_group__iexact=industry)
        return build_report(qs, today=today)

    return cache.get_or_set(key, build, CACHE_SECONDS)


def filing_changes(earlier, later):
    """Differences between two dated disclosures, not new capital or investors.

    Missing and invalid negative values stay unavailable; reported zero is a
    number. Same-day filings have no reliable sequence in the stored date field.
    """
    if earlier.issuer_id != later.issuer_id:
        raise ValueError("Compare records with the same issuer CIK.")
    if earlier.accession_number == later.accession_number:
        raise ValueError("Choose two different accession numbers.")
    if earlier.filing_date > later.filing_date:
        raise ValueError("The earlier filing must precede the later filing.")
    same_day = earlier.filing_date == later.filing_date
    fields = [
        ("total_offering_amount", "Reported offering amount", True),
        ("total_amount_sold", "Reported amount sold", True),
        ("num_investors", "Reported investor count", False),
        ("minimum_investment", "Reported minimum investment", True),
    ]
    rows = []
    for field, label, money in fields:
        before, after = getattr(earlier, field), getattr(later, field)
        before = before if before is not None and before >= 0 else None
        after = after if after is not None and after >= 0 else None
        delta = (
            after - before
            if before is not None and after is not None and not same_day
            else None
        )
        rows.append(
            dict(
                field=field,
                label=label,
                money=money,
                earlier=before,
                later=after,
                delta=delta,
            )
        )
    return dict(earlier=earlier, later=later, rows=rows, same_day=same_day)


def category_report(**scope):
    # Copy the outer dict: do not mutate a cached category report with view state.
    report = activity_report(**scope)
    overall = activity_report()
    return dict(
        report,
        dataset_filings=overall["current"]["filings"],
        dataset_share=percent(
            report["current"]["filings"], overall["current"]["filings"]
        ),
    )
