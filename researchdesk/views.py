import csv
import io
import json
import re
from datetime import timedelta
from html import escape
from urllib.parse import urlencode
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, Q, Case, When, Value, BooleanField
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from config.metadata import metadata
from content.models import Article
from filings.exports import csv_safe_cell
from filings.models import Issuer, IngestionJob
from .analysis import REPORTS, analysis, period, scope_queryset, indexable_report
from .coverage import calendar_rows
from .evidence import MODELS, extract, record, EXTRACTION_VERSION
from .forms import CollectionForm, ItemForm, ReaderRequestForm
from .models import (
    Collection,
    Contributor,
    CoverageDay,
    DisclosureEvidence,
    OfferingLink,
    ReaderRequest,
    ResearchEdition,
    ResearchItem,
    ResearchJob,
)


def page(request, template, title, **context):
    context.update(
        metadata(
            title,
            title
            + ". Research stored SEC disclosures with calculation definitions, source links and explicit coverage limits.",
        )
    )
    context.setdefault("canonical_path", request.path)
    context["research_page"] = title
    context["heading"] = title
    response = render(request, "researchdesk/" + template, context)
    if request.user.is_authenticated or template in {"feedback.html", "thanks.html"}:
        response["Cache-Control"] = "private, no-store"
    return response


def index(request):
    return page(
        request,
        "index.html",
        "Research workbench",
        reports=[
            {"slug": s, "title": v[0], "dataset": v[1]} for s, v in REPORTS.items()
        ],
    )


def report(request, slug):
    if slug not in REPORTS:
        raise Http404
    errors = []
    data = None
    try:
        data = analysis(slug, request.GET)
    except (ValueError, TypeError, OverflowError) as exc:
        errors = [str(exc)]
    if errors or not indexable_report(data):
        request.seo_noindex = True
    if data:
        data["columns"] = list(
            dict.fromkeys(k for row in data["rows"] for k in row if k != "label")
        )
        data["display_rows"] = [
            {"label": r["label"], "cells": [r.get(k) for k in data["columns"]]}
            for r in data["rows"]
        ]
    drilldown = {}
    if data:
        drilldown = {
            "dataset": data["dataset"],
            "from": data["start"],
            "to": data["end"],
            **{key: value for key, value in data.get("filters", {}).items() if value},
        }
        if slug in {"offering-distribution", "minimum-investment", "investor-counts"}:
            drilldown["initial"] = "1"
    return page(
        request,
        "report.html",
        REPORTS[slug][0],
        data=data,
        slug=slug,
        errors=errors,
        query=request.GET.urlencode(),
        drilldown_query=urlencode(drilldown),
    )


def download(request, slug, format):
    if slug not in REPORTS or format not in {"csv", "json", "svg"}:
        raise Http404
    try:
        data = analysis(slug, request.GET)
    except (ValueError, TypeError, OverflowError) as exc:
        return HttpResponseBadRequest(str(exc))
    if format == "json":
        response = JsonResponse(
            data, encoder=DjangoJSONEncoder, json_dumps_params={"indent": 2}
        )
    elif format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Report", data["title"]])
        writer.writerow(["Period", data["start"], data["end"]])
        writer.writerow(["Calculated UTC", data["calculated_at"]])
        writer.writerow(["Method", data["method"]])
        writer.writerow(
            ["Filters", json.dumps(data.get("filters", {}), sort_keys=True)]
        )
        for limitation in data["limitations"]:
            writer.writerow(["Limit", limitation])
        keys = list(dict.fromkeys(k for row in data["rows"] for k in row))
        writer.writerow(keys)
        for row in data["rows"]:
            writer.writerow([csv_safe_cell(row.get(k, "")) for k in keys])
        writer.writerow([])
        writer.writerow(["Sources"])
        for source in data["sources"]:
            writer.writerow(
                [source["accession_number"], source["filing_date"], source["url"]]
            )
        response = HttpResponse(
            buffer.getvalue(), content_type="text/csv; charset=utf-8"
        )
    else:
        rows = data["rows"][:20]
        if slug in {"offering-distribution", "minimum-investment", "investor-counts"}:
            rows = [
                row
                for row in rows
                if "percentile" in row["label"].lower() or row["label"] == "Median"
            ]
        numbers = []
        for row in rows:
            candidate = next(
                (
                    row.get(k)
                    for k in ["filings", "current", "changed_pairs", "value"]
                    if row.get(k) is not None
                ),
                0,
            )
            try:
                numbers.append(max(0, float(candidate)))
            except (TypeError, ValueError):
                numbers.append(0)
        maximum = max(numbers, default=0) or 1
        height = 240 + len(rows) * 45
        elements = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}" viewBox="0 0 1100 {height}" role="img"><title>{escape(data["title"])}</title><desc>{escape(data["method"])}</desc><rect width="100%" height="100%" fill="white"/><g font-family="Arial,sans-serif" fill="#172554"><text x="24" y="32" font-size="22">{escape(data["title"])}</text><text x="24" y="58" font-size="14">{data["start"]}–{data["end"]} · Stored disclosures; no capital totals</text>'
        ]
        scope = (
            "; ".join(
                key + ": " + str(value)
                for key, value in data.get("filters", {}).items()
                if value
            )
            or "All eligible stored disclosures in the period"
        )
        elements.append(f'<text x="24" y="80" font-size="13">{escape(scope)}</text>')
        for i, (row, value) in enumerate(zip(rows, numbers)):
            y = 125 + i * 45
            elements.append(
                f'<text x="24" y="{y}" font-size="13">{escape(str(row["label"])[:45])}</text><rect x="400" y="{y-15}" width="{value/maximum*520:.2f}" height="22" fill="#6366f1"/><text x="940" y="{y}" font-size="13">{escape(str(value))}</text>'
            )
        elements.append(
            f'<text x="24" y="{height-40}" font-size="12">Form D Explorer · {escape(data["calculated_at"])} · {request.build_absolute_uri("/research/analysis/"+slug+"/")}</text></g></svg>'
        )
        response = HttpResponse("".join(elements), content_type="image/svg+xml")
        response["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'none'; sandbox"
        )
    response["Content-Disposition"] = (
        f'attachment; filename="{slug}-{data["start"]}-{data["end"]}.{format}"'
    )
    response["X-Robots-Tag"] = "noindex"
    return response


def disclosures(request):
    request.seo_noindex = True
    dataset = request.GET.get("dataset", "d")
    if dataset not in MODELS:
        raise Http404
    try:
        start, end = period(request.GET)
    except (ValueError, TypeError, OverflowError) as exc:
        return HttpResponseBadRequest(str(exc))
    from filings.search_ui import page_context

    qs = (
        scope_queryset(dataset, start, end, request.GET)
        .select_related("issuer")
        .defer("raw_xml")
        .order_by("-filing_date", "-accession_number")
    )
    return page(
        request,
        "disclosures.html",
        "Underlying disclosures",
        dataset=dataset,
        start=start,
        end=end,
        **page_context(request, qs),
    )


def evidence(request, dataset, accession):
    if dataset not in MODELS or not re.fullmatch(
        r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession
    ):
        raise Http404
    item = get_object_or_404(
        MODELS[dataset].objects.select_related("issuer"), accession_number=accession
    )
    # A bounded local preview makes provenance useful before extraction backfills.
    proof = (
        DisclosureEvidence.objects.filter(
            dataset=dataset, accession=accession, extraction_version=EXTRACTION_VERSION
        )
        .order_by("-extracted_at")
        .first()
    )
    preview = extract(dataset, item)
    if proof and proof.source_hash == preview["source_hash"]:
        values = {
            "identity": proof.identity,
            "facts": proof.facts,
            "source_url": proof.source_url,
            "issues": proof.issues,
            "source_hash": proof.source_hash,
            "accepted_at": proof.accepted_at,
            "references": proof.references,
        }
    else:
        values = preview
    if not values.get("accepted_at"):
        metadata_job = IngestionJob.objects.filter(
            dataset=dataset, kind="metadata", key=accession, state="succeeded"
        ).first()
        if metadata_job and metadata_job.entry.get("accepted_at"):
            from django.utils.dateparse import parse_datetime

            values["accepted_at"] = parse_datetime(metadata_job.entry["accepted_at"])
    return page(
        request,
        "evidence.html",
        "Source evidence for " + accession,
        item=item,
        dataset=dataset,
        proof=values,
        reference_rows=[
            {
                "accession": ref,
                "available": MODELS[dataset]
                .objects.filter(accession_number=ref, issuer_id=item.issuer_id)
                .exists(),
            }
            for ref in values.get("references", [])[:100]
        ],
        facts=[
            dict(field=k, **v)
            for k, v in values["facts"].items()
            if isinstance(v, dict)
        ],
    )


def source_download(request, dataset, accession):
    if dataset not in MODELS:
        raise Http404
    item = get_object_or_404(MODELS[dataset], accession_number=accession)
    if not item.raw_xml:
        raise Http404("Stored source document unavailable.")
    response = HttpResponse(item.raw_xml, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{accession}.txt"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    response["X-Robots-Tag"] = "noindex"
    return response


def brief(request, cik):
    issuer = get_object_or_404(Issuer, cik=cik)
    filings = list(
        issuer.filings.defer("raw_xml").order_by("-filing_date", "-accession_number")[
            :100
        ]
    )
    links = OfferingLink.objects.filter(
        dataset="d", cik=cik, verified_at__isnull=False, verified_by__isnull=False
    )
    return page(
        request,
        "brief.html",
        issuer.name + " research brief",
        issuer=issuer,
        filings=filings,
        links=links,
        as_of=timezone.now(),
    )


def compare_issuers(request):
    request.seo_noindex = True
    raw = request.GET.get("ciks", "")
    errors = []
    rows = []
    ids = [x.strip() for x in raw.split(",") if x.strip()]
    if len(ids) > 5 or any(not re.fullmatch(r"[0-9]{1,10}", i) for i in ids):
        errors = ["Choose up to five numeric CIKs, separated by commas."]
    else:
        seen = set()
        for cik in ids:
            issuer = Issuer.objects.filter(
                cik__in=[cik, cik.zfill(10), cik.lstrip("0") or "0"]
            ).first()
            if not issuer:
                errors.append("A selected CIK is not available in the stored dataset.")
                continue
            if issuer.pk in seen:
                continue
            seen.add(issuer.pk)
            qs = issuer.filings.defer("raw_xml").order_by(
                "-filing_date", "-accession_number"
            )
            rows.append({"issuer": issuer, "count": qs.count(), "latest": qs.first()})
    return page(
        request,
        "compare_issuers.html",
        "Compare issuer disclosures",
        raw=raw,
        rows=rows,
        errors=errors,
    )


@login_required
def collections(request):
    request.seo_noindex = True
    form = CollectionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        from django.db import transaction
        from accounts.models import User

        with transaction.atomic():
            User.objects.select_for_update().get(pk=request.user.pk)
            if Collection.objects.filter(owner=request.user).count() >= 100:
                form.add_error(None, "An account can keep up to 100 collections.")
            else:
                obj = form.save(commit=False)
                obj.owner = request.user
                obj.save()
                return redirect("researchdesk:collection", pk=obj.pk)
    return page(
        request,
        "collections.html",
        "Private research collections",
        collections=Collection.objects.filter(owner=request.user).order_by(
            "-created_at"
        ),
        form=form,
    )


@login_required
def collection(request, pk):
    request.seo_noindex = True
    obj = get_object_or_404(Collection, pk=pk, owner=request.user)
    form = ItemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data
        from django.db import transaction

        with transaction.atomic():
            obj = Collection.objects.select_for_update().get(pk=pk, owner=request.user)
            existing = obj.items.filter(
                dataset=values["dataset"], reference=values["reference"]
            ).exists()
            if not existing and obj.items.count() >= 500:
                form.add_error(None, "A collection can keep up to 500 source notes.")
            else:
                ResearchItem.objects.update_or_create(
                    collection=obj,
                    dataset=values["dataset"],
                    reference=values["reference"],
                    defaults={"note": values["note"]},
                )
                return redirect("researchdesk:collection", pk=pk)
    return page(
        request,
        "collection.html",
        obj.name,
        collection=obj,
        items=obj.items.order_by("-updated_at"),
        form=form,
    )


@login_required
@require_POST
def delete_item(request, pk):
    item = get_object_or_404(ResearchItem, pk=pk, collection__owner=request.user)
    collection_pk = item.collection_id
    item.delete()
    return redirect("researchdesk:collection", pk=collection_pk)


@login_required
@require_POST
def delete_collection(request, pk):
    get_object_or_404(Collection, pk=pk, owner=request.user).delete()
    return redirect("researchdesk:collections")


def feedback(request):
    request.seo_noindex = True
    form = ReaderRequestForm(
        request.POST or None,
        initial={
            k: request.GET.get(k, "") for k in ["kind", "dataset", "reference", "field"]
        },
    )
    if request.method == "POST" and form.is_valid():
        if not request.session.session_key:
            request.session.create()
        key = "researchdesk:feedback:" + request.session.session_key
        if not cache.add(key, True, 60):
            form.add_error(
                None, "Please wait a minute before submitting another request."
            )
        else:
            form.save()
            return page(request, "thanks.html", "Request received")
    return page(
        request,
        "feedback.html",
        "Corrections, research requests and usability participation",
        form=form,
    )


def editions(request):
    if not ResearchEdition.objects.filter(
        status="published", published_at__lte=timezone.now()
    ).exists():
        request.seo_noindex = True
    return page(
        request,
        "editions.html",
        "Research editions and corrections",
        editions=ResearchEdition.objects.filter(
            status="published", published_at__lte=timezone.now()
        ).select_related("author", "previous"),
    )


def edition(request, pk):
    obj = get_object_or_404(
        ResearchEdition.objects.select_related("author", "previous"),
        pk=pk,
        status="published",
        published_at__lte=timezone.now(),
    )
    return page(
        request,
        "edition.html",
        obj.title,
        edition=obj,
        reviews=obj.reviews.select_related("reviewer").all(),
    )


def contributor(request, slug):
    obj = get_object_or_404(Contributor, slug=slug, verified_at__isnull=False)
    return page(
        request,
        "contributor.html",
        obj.name,
        contributor=obj,
        editions=obj.editions.filter(
            status="published", published_at__lte=timezone.now()
        ),
    )


@staff_member_required
def operations(request):
    request.seo_noindex = True
    from filings.ingest.monitoring import freshness_report

    health = freshness_report()
    dataset = request.GET.get("dataset", "d")
    if dataset not in MODELS:
        dataset = "d"
    return page(
        request,
        "operations.html",
        "Ingestion and research operations",
        health=health,
        maintenance_pulse=ResearchJob.objects.filter(kind="maintenance-heartbeat")
        .order_by("-finished_at")
        .first(),
        calendar=calendar_rows(dataset),
        dataset=dataset,
        jobs=IngestionJob.objects.exclude(state="succeeded").order_by("source_date")[
            :100
        ],
        requests=ReaderRequest.objects.order_by("-created_at")[:50],
        aging_guides=Article.objects.filter(
            published_at__lte=timezone.now(),
            updated_at__lt=timezone.now() - timedelta(days=180),
        ).only("title", "slug", "updated_at"),
        research_jobs=ResearchJob.objects.defer("payload").order_by("-created_at")[:50],
    )


@staff_member_required
@require_POST
def queue_operation(request):
    kind = request.POST.get("kind")
    dataset = request.POST.get("dataset", "d")
    if (
        kind not in {"reconcile", "extract", "monthly-draft", "recover"}
        or dataset not in MODELS
    ):
        return HttpResponseBadRequest("Choose a supported operation.")
    ResearchJob.objects.create(
        owner=request.user, kind=kind, params={"dataset": dataset}
    )
    return redirect("researchdesk:operations")


@login_required
def exports(request):
    import uuid
    from django.db import transaction, IntegrityError
    from django.http import QueryDict
    from filings.search_params import normalize_search_params, SearchValidationError

    request.seo_noindex = True
    error = ""
    if request.method == "POST":
        try:
            dataset = request.POST.get("dataset", "d")
            if dataset not in {"d", "c", "a", "adv"}:
                raise ValueError("Choose a supported dataset.")
            key = uuid.UUID(request.POST.get("request_key", ""))
            query = request.POST.get("query", "")
            if len(query) > 4000:
                raise ValueError("Search query exceeds the supported limit.")
            params = normalize_search_params(QueryDict(query))
            filters = {k: params.getlist(k) for k in params}
            with transaction.atomic():
                from accounts.models import User

                owner = User.objects.select_for_update().get(pk=request.user.pk)
                if not owner.is_active or (
                    not owner.is_paid
                    and not owner.export_tokens.filter(used_at__isnull=True).exists()
                ):
                    raise ValueError(
                        "An active subscription or unused export credit is required."
                    )
                existing = (
                    ResearchJob.objects.defer("payload").filter(request_key=key).first()
                )
                if existing and existing.owner_id != owner.pk:
                    raise ValueError("Use a new export request key.")
                if (
                    not existing
                    and ResearchJob.objects.filter(
                        owner=owner, kind="export", state__in=["pending", "running"]
                    ).count()
                    >= 5
                ):
                    raise ValueError(
                        "Wait for an existing export to finish before adding more."
                    )
                job = existing or ResearchJob.objects.create(
                    owner=owner,
                    kind="export",
                    request_key=key,
                    params={"dataset": dataset, "filters": filters},
                )
            return redirect("researchdesk:export_status", pk=job.pk)
        except (ValueError, SearchValidationError, IntegrityError) as exc:
            error = str(exc)
    dataset = request.POST.get("dataset", request.GET.get("dataset", "d"))
    if dataset not in {"d", "c", "a", "adv"}:
        dataset = "d"
    query = request.POST.get("query", request.GET.get("query", ""))[:4000]
    selected = QueryDict(query)
    return page(
        request,
        "exports.html",
        "Prepare a background export",
        selected_dataset=dataset,
        selected_query=query,
        selected_filters=list(selected.lists()),
        request_key=uuid.uuid4(),
        error=error,
        jobs=ResearchJob.objects.defer("payload")
        .filter(owner=request.user, kind="export")
        .order_by("-created_at")[:25],
    )


@login_required
def export_status(request, pk):
    request.seo_noindex = True
    job = get_object_or_404(
        ResearchJob.objects.defer("payload").annotate(
            has_payload=Case(
                When(payload__isnull=False, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        ),
        pk=pk,
        owner=request.user,
        kind="export",
    )
    available = (
        job.state == "finished"
        and job.has_payload
        and job.finished_at is not None
        and job.finished_at >= timezone.now() - timedelta(hours=24)
    )
    error = (
        "The export could not be prepared. No file or export charge was completed. Check your access and try a new request."
        if job.state == "failed"
        else ""
    )
    return page(
        request,
        "export_status.html",
        "Export progress",
        job=job,
        download_available=available,
        public_error=error,
    )


@login_required
def export_download(request, pk):
    job = get_object_or_404(
        ResearchJob,
        pk=pk,
        owner=request.user,
        kind="export",
        state="finished",
        finished_at__gte=timezone.now() - timedelta(hours=24),
    )
    if job.payload is None:
        raise Http404("This generated download has expired.")
    response = HttpResponse(bytes(job.payload), content_type=job.content_type)
    response["Content-Disposition"] = f'attachment; filename="{job.filename}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def coverage_calendar(request):
    dataset = request.GET.get("dataset", "d")
    if dataset not in MODELS:
        return HttpResponseBadRequest("Choose Form D, Form C or Reg A.")
    return page(
        request,
        "calendar.html",
        "Daily import reconciliation",
        dataset=dataset,
        datasets=[("d", "Form D"), ("c", "Form C"), ("a", "Reg A")],
        days=list(reversed(calendar_rows(dataset))),
    )
