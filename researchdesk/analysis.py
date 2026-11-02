"""Original, bounded descriptive analyses over stored SEC disclosures."""

import calendar
from datetime import date, timedelta
from decimal import Decimal
from django.core.cache import cache
from django.db.models import Count, Q, Max, Min
from django.db.models.functions import Trim
from django.utils import timezone
from filings.intelligence import AMENDMENT, month_offset, percent
from filings.models import Filing
from .evidence import MODELS
from .models import DisclosureEvidence

REPORTS = {
    "year-over-year": ("Filing activity compared with the previous year", "d"),
    "exemptions": ("Reported exemption usage", "d"),
    "fund-categories": ("Fund categories reported in source disclosures", "d"),
    "industry-mix": ("Pooled investment fund and other reported industries", "d"),
    "offering-distribution": ("Distribution of reported offering amounts", "d"),
    "minimum-investment": ("Distribution of reported minimum investments", "d"),
    "investor-counts": ("Distribution of reported investor counts", "d"),
    "amendment-fields": ("Changes between explicitly linked disclosures", "d"),
    "crowdfunding": ("Crowdfunding filing activity and disclosure coverage", "c"),
    "regulation-a": ("Regulation A submission types and disclosure coverage", "a"),
    "monthly-edition": ("Monthly disclosure activity and source checks", "d"),
}


def period(params):
    from zoneinfo import ZoneInfo

    today = timezone.now().astimezone(ZoneInfo("America/New_York")).date()
    mode = params.get("period", "month")
    end = month_offset(today, 0) - timedelta(days=1)
    start = end.replace(day=1)
    if mode == "quarter":
        current = today.replace(month=((today.month - 1) // 3) * 3 + 1, day=1)
        end = current - timedelta(days=1)
        start = end.replace(month=((end.month - 1) // 3) * 3 + 1, day=1)
    elif mode == "year":
        start = date(today.year - 1, 1, 1)
        end = date(today.year - 1, 12, 31)
    elif mode != "month" and mode != "custom":
        raise ValueError("Choose month, quarter, year, or custom dates.")
    if params.get("from"):
        start = date.fromisoformat(params["from"])
    if params.get("to"):
        end = date.fromisoformat(params["to"])
    if start > end or (end - start).days > 366 or end > today:
        raise ValueError(
            "Choose a reporting period of at most 367 days, ending no later than today."
        )
    return start, end


def scope_queryset(dataset, start, end, params=None):
    qs = (
        MODELS[dataset]
        .objects.filter(filing_date__range=[start, end])
        .alias(research_name=Trim("issuer__name"))
        .exclude(research_name="")
        .order_by()
    )
    params = params or {}
    from filings.states import US_STATES
    from filings.industry import INDUSTRY_GROUPS

    if params.get("state") and params["state"] not in dict(US_STATES):
        raise ValueError("Choose a recognized state.")
    if params.get("industry") and params["industry"] not in INDUSTRY_GROUPS:
        raise ValueError("Choose a recognized reported industry.")
    if params.get("state"):
        qs = qs.filter(issuer__state=params["state"])
    if dataset == "d" and params.get("industry"):
        qs = qs.filter(industry_group=params["industry"])
    if params.get("initial") == "1":
        qs = qs.exclude(Q(is_amendment=True) | Q(form_type__contains="/A"))
    return qs


def counts(qs, dataset):
    amount = "maximum_offering_amount" if dataset == "c" else "total_offering_amount"
    amendment = (
        AMENDMENT
        if dataset == "d"
        else Q(is_amendment=True) | Q(form_type__contains="/A")
    )
    return qs.aggregate(
        filings=Count("pk"),
        issuers=Count("issuer_id", distinct=True),
        amendments=Count("pk", filter=amendment),
        originals=Count("pk", filter=~amendment),
        offering_known=Count("pk", filter=Q(**{amount + "__gte": 0})),
        earliest=Min("filing_date"),
    )


def quantile(values, p):
    if not values:
        return None
    position = Decimal(len(values) - 1) * Decimal(str(p))
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return Decimal(values[lower]) + (
        Decimal(values[upper]) - Decimal(values[lower])
    ) * (position - lower)


def distribution(qs, field):
    initial = qs.exclude(AMENDMENT)
    total = initial.count()
    valid = initial.filter(**{field + "__gte": 0})
    n = valid.count()
    # Never silently sample or aggregate monetary amendments.
    if n > 50000:
        return [
            {
                "label": "Narrow the period: more than 50,000 usable initial disclosures",
                "value": None,
            }
        ], {"eligible": total, "usable": n, "unavailable": total - n, "bounded": True}
    values = list(valid.order_by(field).values_list(field, flat=True))
    rows = [
        {"label": label, "value": str(quantile(values, p)) if values else None}
        for label, p in [
            ("10th percentile", 0.1),
            ("25th percentile", 0.25),
            ("Median", 0.5),
            ("75th percentile", 0.75),
            ("90th percentile", 0.9),
        ]
    ]
    rows.extend(
        [
            {"label": "Usable numeric disclosures", "value": n},
            {"label": "Reported zero", "value": sum(v == 0 for v in values)},
            {"label": "Unavailable or invalid", "value": total - n},
        ]
    )
    return rows, {
        "eligible": total,
        "usable": n,
        "unavailable": total - n,
        "bounded": False,
    }


def build_analysis(slug, params):
    title, dataset = REPORTS[slug]
    start, end = period(params)
    qs = scope_queryset(dataset, start, end, params)
    totals = counts(qs, dataset)
    result = {
        "slug": slug,
        "title": title,
        "dataset": dataset,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "calculated_at": timezone.now().isoformat(),
        "totals": totals,
        "filters": {
            key: params.get(key, "") for key in ["state", "industry", "initial"]
        },
        "rows": [],
        "sample": {},
        "method": "Unique stored accessions; issuers are distinct CIKs. Counts describe this dataset, not the entire market. No monetary amounts are summed.",
        "limitations": [
            "A completed calendar period does not prove complete SEC coverage.",
            "Filed disclosures are not SEC approval or investment recommendations.",
        ],
        "sources": list(
            qs.order_by("-filing_date", "-accession_number").values(
                "accession_number", "issuer__cik", "filing_date"
            )[:5]
        ),
    }
    if slug in {"offering-distribution", "minimum-investment", "investor-counts"}:
        field = {
            "offering-distribution": "total_offering_amount",
            "minimum-investment": "minimum_investment",
            "investor-counts": "num_investors",
        }[slug]
        result["rows"], result["sample"] = distribution(qs, field)
        result[
            "method"
        ] += " Only initial notices are used for these distributions. Linear quantiles use rank (n−1)×p; numeric zero is included and missing or negative values are excluded. Units are investor counts or source-reported USD, as labelled."
    elif slug == "year-over-year":

        def previous(day):
            return day.replace(
                year=day.year - 1,
                day=min(day.day, calendar.monthrange(day.year - 1, day.month)[1]),
            )

        earlier = counts(
            scope_queryset(dataset, previous(start), previous(end), params), dataset
        )
        usable_comparison = earlier["filings"] >= 20 and totals["filings"] >= 20
        result["sample"] = {
            "current_filings": totals["filings"],
            "previous_filings": earlier["filings"],
            "minimum_window_observations_for_percent_change": 20,
        }
        if not usable_comparison:
            result["limitations"].append(
                "Percentage changes are suppressed when either window has fewer than 20 stored filings. Sparse or missing observations do not establish low or zero market activity. This display rule is not a completeness certification."
            )
        for key in ["filings", "issuers", "originals", "amendments"]:
            result["rows"].append(
                {
                    "label": key.replace("_", " ").title(),
                    "previous": earlier[key],
                    "current": totals[key],
                    "difference": totals[key] - earlier[key],
                    "percent": (
                        str(percent(totals[key] - earlier[key], earlier[key]))
                        if earlier[key] and usable_comparison
                        else None
                    ),
                }
            )
        result["previous_start"] = previous(start).isoformat()
        result["previous_end"] = previous(end).isoformat()
        result["limitations"].append(
            "Equal calendar windows can contain different publication days and import gaps. Changes are descriptive, not causal."
        )
    elif slug == "industry-mix":
        result["rows"] = list(
            qs.values("industry_group")
            .annotate(
                filings=Count("pk"),
                issuers=Count("issuer_id", distinct=True),
                amendments=Count("pk", filter=AMENDMENT),
            )
            .order_by("-filings", "industry_group")
        )
        for row in result["rows"]:
            row["label"] = row.pop("industry_group") or "Not disclosed"
            row["share"] = (
                str(percent(row["filings"], totals["filings"]))
                if totals["filings"]
                else None
            )
        result["limitations"].append(
            "Industry is issuer-reported. Pooled Investment Fund is a classification, not a verified business model."
        )
    elif slug in {"exemptions", "fund-categories"}:
        grouped = {}
        seen = set()
        usable = 0
        for evidence in (
            DisclosureEvidence.objects.filter(
                dataset="d", accession__in=qs.values("accession_number")
            )
            .order_by("accession", "-extracted_at")
            .iterator()
        ):
            if evidence.accession in seen:
                continue
            seen.add(evidence.accession)
            fields = evidence.facts.get("classifications", [])
            allowed = (
                {"item", "federalExemption", "federalExemptions"}
                if slug == "exemptions"
                else {"typeOfPooledInvestmentFund", "investmentFundType"}
            )
            values = {r["raw"] for r in fields if r["field"] in allowed}
            if values:
                usable += 1
            for value in values:
                grouped[value] = grouped.get(value, 0) + 1
        result["rows"] = [
            {"label": key, "filings": count} for key, count in sorted(grouped.items())
        ]
        result["sample"] = {
            "not_extracted_or_classification_unavailable": totals["filings"] - usable,
            "scope_filings": totals["filings"],
        }
        result["limitations"].append(
            "Only extracted source classifications are counted; a filing may report multiple classifications. Unextracted records are not evidence of no classification."
        )
    elif slug == "amendment-fields":
        from .evidence import record
        from django.db.models import OuterRef, Subquery

        latest = (
            DisclosureEvidence.objects.filter(
                dataset="d", accession=OuterRef("accession")
            )
            .order_by("-extracted_at", "-pk")
            .values("pk")[:1]
        )
        candidates = (
            DisclosureEvidence.objects.filter(
                dataset="d",
                accession__in=qs.values("accession_number"),
                pk=Subquery(latest),
            )
            .exclude(references=[])
            .order_by("accession")[:1000]
        )
        pairs = 0
        grouped = {}
        seen = set()
        for proof in candidates:
            for earlier in proof.references:
                if (earlier, proof.accession) in seen:
                    continue
                seen.add((earlier, proof.accession))
                try:
                    a = record("d", earlier)
                    b = record("d", proof.accession)
                except MODELS["d"].DoesNotExist:
                    continue
                if (
                    a.issuer_id != b.issuer_id
                    or b.issuer.cik.lstrip("0") != proof.cik.lstrip("0")
                    or not b.is_amendment
                    and b.form_type != "D/A"
                ):
                    continue
                pairs += 1
                for field in [
                    "total_offering_amount",
                    "total_amount_sold",
                    "num_investors",
                    "minimum_investment",
                ]:
                    if getattr(a, field) != getattr(b, field):
                        grouped[field] = grouped.get(field, 0) + 1
        result["rows"] = [
            {"label": key.replace("_", " "), "changed_pairs": n}
            for key, n in sorted(grouped.items())
        ]
        result["sample"] = {"source_linked_pairs": pairs, "candidate_limit": 1000}
        result["limitations"].append(
            "Only explicit previous-accession references in the latest extracted source, with matching issuer CIKs and a later amendment, are compared. These source links are not independent editorial reviews. A changed amount is not independently verified new capital. At most 1,000 source candidates are examined."
        )
    else:
        for row in (
            qs.values("form_type")
            .annotate(filings=Count("pk"), issuers=Count("issuer_id", distinct=True))
            .order_by("form_type")
        ):
            result["rows"].append(
                {
                    "label": row["form_type"],
                    "filings": row["filings"],
                    "issuers": row["issuers"],
                }
            )
        result["sample"] = {
            "numeric_offering_disclosures": totals["offering_known"],
            "unavailable_offering_disclosures": totals["filings"]
            - totals["offering_known"],
        }
        if dataset == "a":
            result["limitations"].append(
                "Reg A filing types and withdrawals are disclosures, not proof of qualification, completion or money received."
            )
    for source in result["sources"]:
        source["url"] = (
            f'https://www.sec.gov/Archives/edgar/data/{int(source["issuer__cik"])}/{source["accession_number"].replace("-","")}/{source["accession_number"]}-index.htm'
        )
        source["filing_date"] = source["filing_date"].isoformat()
    import json
    from django.core.serializers.json import DjangoJSONEncoder

    return json.loads(json.dumps(result, cls=DjangoJSONEncoder))


def analysis(slug, params):
    import hashlib, json

    start, end = period(params)
    dataset = REPORTS[slug][1]
    stamp = MODELS[dataset].objects.aggregate(latest=Max("updated_at"))["latest"]
    proof = DisclosureEvidence.objects.filter(dataset=dataset).aggregate(
        latest=Max("last_checked_at")
    )["latest"]
    key = (
        "researchdesk:analysis:v2:"
        + hashlib.sha256(
            json.dumps(
                [
                    slug,
                    str(start),
                    str(end),
                    params.get("state", ""),
                    params.get("industry", ""),
                    params.get("initial", ""),
                    str(stamp),
                    str(proof),
                ]
            ).encode()
        ).hexdigest()
    )
    return cache.get_or_set(key, lambda: build_analysis(slug, params), 900)


def indexable_report(data):
    return bool(
        data["totals"]["filings"]
        and data["rows"]
        and data.get("sample", {}).get("usable") != 0
    )
