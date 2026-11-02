"""One SQL aggregate and one cache entry for each bounded category comparison."""

import hashlib, json
from django.core.cache import cache
from django.db.models import Count, Max, Q
from django.utils import timezone
from filings.intelligence import research_queryset, AMENDMENT, percent


def snapshot(kind, choices, start, end):
    key = (
        "researchdesk:comparison:v1:"
        + hashlib.sha256(
            json.dumps([kind, choices, str(start), str(end)]).encode()
        ).hexdigest()
    )

    def build():
        qs = research_queryset().filter(filing_date__range=[start, end])
        aggregates = {"total": Count("pk"), "source_updated_at": Max("updated_at")}
        for i, choice in enumerate(choices):
            match = (
                Q(issuer__state=choice)
                if kind == "state"
                else Q(industry_group__iexact=choice)
            )
            aggregates.update(
                {
                    f"{i}_filings": Count("pk", filter=match),
                    f"{i}_issuers": Count("issuer_id", distinct=True, filter=match),
                    f"{i}_amendments": Count("pk", filter=match & AMENDMENT),
                    f"{i}_known": Count(
                        "pk", filter=match & Q(total_offering_amount__gte=0)
                    ),
                    f"{i}_first": Max("filing_date", filter=match),
                }
            )
        values = qs.aggregate(**aggregates)
        rows = []
        for i, choice in enumerate(choices):
            count = values[f"{i}_filings"]
            known = values[f"{i}_known"]
            rows.append(
                {
                    "value": choice,
                    "filings": count,
                    "issuers": values[f"{i}_issuers"],
                    "amendments": values[f"{i}_amendments"],
                    "offering_known": known,
                    "offering_missing": count - known,
                    "share": percent(count, values["total"]),
                    "latest": values[f"{i}_first"],
                }
            )
        return {
            "rows": rows,
            "total": values["total"],
            "source_updated_at": values["source_updated_at"],
            "calculated_at": timezone.now(),
        }

    return cache.get_or_set(key, build, 900)
