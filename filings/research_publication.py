"""Bounded snapshot calculations for deliberately curated research publications.

This does not publish articles or schedule content. Call within a repeatable-read
transaction when creating a frozen production snapshot. Only public filing data
is returned; no account, contact enrichment, or subscription records are read.
"""
from django.db.models import Count, Q
from django.db.models.functions import Trim
from django.utils import timezone

from .intelligence import AMENDMENT, month_offset, percent


def period_metrics(queryset, month):
    qs = queryset.order_by().filter(filing_date__gte=month, filing_date__lt=month_offset(month, 1))
    stats = qs.aggregate(
        filings=Count('pk', distinct=True), issuers=Count('issuer_id', distinct=True),
        originals=Count('pk', distinct=True, filter=~AMENDMENT),
        amendments=Count('pk', distinct=True, filter=AMENDMENT),
        offering_known=Count('pk', distinct=True, filter=Q(total_offering_amount__gte=0)),
        sold_known=Count('pk', distinct=True, filter=Q(total_amount_sold__gte=0)),
        investors_known=Count('pk', distinct=True, filter=Q(num_investors__gte=0)),
        offering_zero=Count('pk', distinct=True, filter=Q(total_offering_amount=0)),
        sold_zero=Count('pk', distinct=True, filter=Q(total_amount_sold=0)),
        investors_zero=Count('pk', distinct=True, filter=Q(num_investors=0)),
    )
    stats['repeat_issuer_ciks'] = qs.values('issuer_id').annotate(n=Count('pk', distinct=True)).filter(n__gt=1).count()
    stats['month'] = month.isoformat()
    stats['amendment_share'] = percent(stats['amendments'], stats['filings'])
    return stats


def month_snapshot(queryset, month, *, today=None):
    today = today or timezone.localdate()
    if month.day != 1 or month >= today.replace(day=1):
        raise ValueError('Use the first day of a completed calendar month.')
    qs = queryset.alias(research_name=Trim('issuer__name')).exclude(research_name='').filter(filing_date__lte=today)
    current = period_metrics(qs, month)
    previous = period_metrics(qs, month_offset(month, -1))
    current_qs = qs.filter(filing_date__gte=month, filing_date__lt=month_offset(month, 1)).order_by()
    industries = list(current_qs.values('industry_group').annotate(
        filings=Count('pk', distinct=True), issuers=Count('issuer_id', distinct=True),
        originals=Count('pk', distinct=True, filter=~AMENDMENT),
        amendments=Count('pk', distinct=True, filter=AMENDMENT),
    ).order_by('-filings', 'industry_group'))
    for row in industries:
        row['dataset_share'] = percent(row['filings'], current['filings'])
    availability = []
    for label, subset in [('Initial notices', current_qs.filter(~AMENDMENT)), ('Amendments', current_qs.filter(AMENDMENT))]:
        values = subset.aggregate(
            filings=Count('pk', distinct=True),
            offering_known=Count('pk', distinct=True, filter=Q(total_offering_amount__gte=0)),
            sold_known=Count('pk', distinct=True, filter=Q(total_amount_sold__gte=0)),
            investors_known=Count('pk', distinct=True, filter=Q(num_investors__gte=0)),
        )
        availability.append(dict(label=label, **values))
    delta = current['filings'] - previous['filings']
    return dict(
        schema_version=1, data_as_of=timezone.now().isoformat(),
        scope='Stored Form D accessions with nonblank issuer names; calendar completion does not certify complete SEC import coverage.',
        current=current, previous=previous, filing_difference=delta,
        filing_change_percent=percent(delta, previous['filings']),
        industries=industries, availability_by_submission=availability,
        definitions={
            'issuer':'Distinct stored CIK, not a brand, fund family, or offering.',
            'amendment':'D/A submission type or extracted amendment flag; each accession counted once.',
            'known':'Nonnegative stored numeric value, including zero; not independently certified completeness.',
            'industry':'Issuer-reported classification on each filing; one CIK may appear in more than one category.',
            'amounts':'No offering/sold amounts are summed. No financing, cash-receipt, investor-identity or national-market conclusion is inferred.',
        },
    )
