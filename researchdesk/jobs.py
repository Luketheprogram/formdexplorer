"""Leased background work. Generate exports before atomically consuming a credit."""

import csv
import json
import io
import uuid
from datetime import timedelta
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q, OuterRef, Subquery
from django.utils import timezone
from accounts.models import User
from filings.exports import csv_safe_cell
from filings.search import build_filing_query
from filings.search_params import normalize_search_params
from .models import ResearchJob, DisclosureEvidence, ResearchEdition
from .evidence import MODELS, materialize, EXTRACTION_VERSION
from .analysis import analysis, period
from .coverage import reconcile_day


class LostLease(Exception):
    pass


def claim(pk):
    now = timezone.now()
    token = uuid.uuid4()
    ResearchJob.objects.filter(pk=pk, attempts__gte=5).filter(
        Q(state="pending") | Q(state="running", lease_until__lte=now)
    ).update(
        state="failed",
        error="Retry budget exhausted after interrupted workers.",
        finished_at=now,
        lease=None,
        lease_until=None,
    )
    changed = (
        ResearchJob.objects.filter(pk=pk, attempts__lt=5)
        .filter(Q(state="pending") | Q(state="running", lease_until__lte=now))
        .update(
            state="running",
            lease=token,
            lease_until=now + timedelta(minutes=15),
            attempts=F("attempts") + 1,
            error="",
        )
    )
    return token if changed else None


def locked(pk, token):
    job = ResearchJob.objects.select_for_update().get(pk=pk)
    if (
        job.state != "running"
        or job.lease != token
        or not job.lease_until
        or job.lease_until <= timezone.now()
    ):
        raise LostLease("Research job lease expired or replaced.")
    return job


def export_payload(params):
    dataset = params.get("dataset", "d")
    if dataset not in {"d", "c", "a", "adv"}:
        raise ValueError("Unsupported export dataset.")
    filters = normalize_search_params(params.get("filters", {}))
    if dataset == "d":
        qs = build_filing_query(filters).defer("raw_xml")
    elif dataset == "c":
        from crowdfunding.views import _build_qs

        qs = _build_qs(filters)
    elif dataset == "a":
        from rega.views import _build_qs

        qs = _build_qs(filters)
    else:
        from advisers.views import _build_queryset

        qs = _build_queryset(filters.get("q", ""))
    rows = list(qs[:5001])
    if len(rows) > 5000:
        raise ValueError(
            "More than 5,000 results. Narrow the search before exporting; no rows were silently omitted."
        )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if dataset == "adv":
        writer.writerow(
            [
                "Firm name",
                "CRD or SEC identifier",
                "Last filed",
                "Regulatory AUM USD",
                "State",
                "Source",
            ]
        )
        for obj in rows:
            writer.writerow(
                [
                    csv_safe_cell(v)
                    for v in [
                        obj.name,
                        obj.crd,
                        obj.last_filed_at,
                        obj.regulatory_aum,
                        obj.state,
                        (
                            f"https://adviserinfo.sec.gov/firm/summary/{obj.crd}"
                            if obj.has_crd
                            else "SEC identifier; inspect adviser profile"
                        ),
                    ]
                ]
            )
    else:
        writer.writerow(
            [
                "Accession",
                "Form type",
                "Filing date",
                "Issuer",
                "CIK",
                "Reported offering USD",
                "Reported sold USD",
                "Source",
            ]
        )
        for obj in rows:
            writer.writerow(
                [
                    csv_safe_cell(v)
                    for v in [
                        obj.accession_number,
                        obj.form_type,
                        obj.filing_date,
                        obj.issuer.name,
                        obj.issuer.cik,
                        getattr(
                            obj,
                            "total_offering_amount",
                            getattr(obj, "maximum_offering_amount", None),
                        ),
                        getattr(obj, "total_amount_sold", None),
                        obj.edgar_url,
                    ]
                ]
            )
    writer.writerow([])
    writer.writerow(
        [
            "# Methods",
            "Stored disclosures matching the selected filters at generation time; not a complete-market estimate. Missing values remain blank. Rows are not summed across amendments.",
        ]
    )
    writer.writerow(
        [
            "# Filters",
            csv_safe_cell(json.dumps(params.get("filters", {}), sort_keys=True)),
        ]
    )
    writer.writerow(["# Generated at UTC", timezone.now().isoformat()])
    writer.writerow(
        [
            "# Sources",
            "Each filing row links to its SEC source. Definitions: https://formdexplorer.com/research/glossary/",
        ]
    )
    payload = buffer.getvalue().encode("utf-8-sig")
    if len(payload) > 10_000_000:
        raise ValueError("Export exceeds the 10 MB limit; narrow the search.")
    return payload, f"{dataset}-disclosures.csv", "text/csv; charset=utf-8"


def extraction_queryset(dataset):
    latest = (
        DisclosureEvidence.objects.filter(
            dataset=dataset,
            accession=OuterRef("accession_number"),
            source_record_updated_at__isnull=False,
            extraction_version=EXTRACTION_VERSION,
        )
        .order_by("-source_record_updated_at")
        .values("source_record_updated_at")[:1]
    )
    return (
        MODELS[dataset]
        .objects.select_related("issuer")
        .exclude(raw_xml="")
        .annotate(proof_input_version=Subquery(latest))
        .filter(
            Q(proof_input_version__isnull=True)
            | Q(updated_at__gt=F("proof_input_version"))
        )
        .order_by("-filing_date", "-pk")
    )


def run(pk):
    token = claim(pk)
    if not token:
        return False
    job = ResearchJob.objects.get(pk=pk)
    payload = None
    filename = ""
    content_type = ""
    try:
        if job.kind == "export":
            payload, filename, content_type = export_payload(job.params)
        elif job.kind == "extract":
            dataset = job.params.get("dataset", "d")
            if dataset not in MODELS:
                raise ValueError("Unsupported dataset.")
            qs = extraction_queryset(dataset)[:500]
            for item in qs.iterator(chunk_size=20):
                materialize(dataset, item)
        elif job.kind == "historical-ingestion":
            from filings.ingest.pipeline import IngestPipeline
            from filings.ingest.edgar_client import EdgarClient

            today = timezone.localdate()
            IngestPipeline(EdgarClient(rate_per_sec=4), store_raw_xml=True).run(
                today, today, historical_only=True, filing_limit=25, retry_limit=1
            )
        elif job.kind == "recover":
            from .recovery import recover

            recover(job.params.get("dataset", "d"), limit=5)
        elif job.kind == "reconcile":
            from filings.models import IngestionJob

            dataset = job.params.get("dataset", "d")
            if dataset not in MODELS:
                raise ValueError("Unsupported dataset.")
            days = (
                IngestionJob.objects.filter(dataset=dataset, kind="index")
                .order_by("-source_date")
                .values_list("source_date", flat=True)[
                    : max(1, min(int(job.params.get("days", 90)), 90))
                ]
            )
            for day in days:
                reconcile_day(dataset, day)
        elif job.kind == "monthly-draft":
            data = analysis("monthly-edition", {})
            from datetime import date

            ResearchEdition.objects.get_or_create(
                series="monthly-disclosures",
                period_start=date.fromisoformat(data["start"]),
                period_end=date.fromisoformat(data["end"]),
                version=1,
                defaults={
                    "title": "Monthly stored Form D disclosures: " + data["start"][:7],
                    "data_as_of": timezone.now(),
                    "snapshot": data,
                    "body": f"This draft contains {data['totals']['filings']} stored submissions from {data['totals']['issuers']} CIKs. Review source examples, coverage and calculations before publication. No monetary amounts are summed.",
                },
            )
        else:
            raise ValueError("Unsupported research operation.")
        with transaction.atomic():
            active = locked(pk, token)
            if job.kind == "export":
                if not job.owner_id:
                    raise PermissionDenied("An export needs an owner.")
                owner = User.objects.select_for_update().get(pk=job.owner_id)
                if not owner.is_active:
                    raise PermissionDenied("The account is inactive.")
                if not owner.is_paid:
                    credit = (
                        owner.export_tokens.select_for_update()
                        .filter(used_at__isnull=True)
                        .first()
                    )
                    if not credit or not credit.consume():
                        raise PermissionDenied(
                            "No unused export credit remains. No file was released."
                        )
                    active.credit_consumed = True
                active.payload = payload
                active.filename = filename
                active.content_type = content_type
            active.state = "finished"
            active.finished_at = timezone.now()
            active.lease = None
            active.lease_until = None
            active.save()
        return True
    except LostLease:
        return False
    except Exception as exc:
        with transaction.atomic():
            try:
                active = locked(pk, token)
            except LostLease:
                return False
            active.state = "failed"
            active.error = f"{type(exc).__name__}: {exc}"[:1000]
            active.finished_at = timezone.now()
            active.lease = None
            active.lease_until = None
            active.save()
        return False
