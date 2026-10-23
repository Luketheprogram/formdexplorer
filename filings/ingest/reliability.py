"""Durable, bounded retries with lease fencing and atomic filing/checkpoint writes."""
import hashlib
import logging
import uuid
from dataclasses import asdict
from collections import defaultdict
from datetime import date, timedelta

from django.db import connection, transaction
from django.db.models import Q, Max, F
from django.utils import timezone

from filings.models import IngestionJob, IngestionRun, IngestionSource
from .calendar import expected_closure
from .edgar_client import retry_after_seconds
from .index_parser import IndexEntry, SourceCIKMismatch, accession_from_filename, iter_business_days

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 8
LEASE_TIME = timedelta(minutes=15)


class LostLease(Exception):
    pass


class RecordingClient:
    def __init__(self, client):
        self.client = client
        self.sources = []

    def get_bytes(self, path):
        content = self.client.get_bytes(path)
        self.sources.append((path if path.startswith("https://") else "https://www.sec.gov" + path, content))
        return content

    def get_text(self, path):
        return self.get_bytes(path).decode("utf-8-sig")


def claim(pk, now=None):
    now = now or timezone.now()
    token = uuid.uuid4()
    IngestionJob.objects.filter(pk=pk, attempts__gte=MAX_ATTEMPTS).filter(
        Q(state="pending", next_attempt_at__lte=now) | Q(state="running", lease_until__lte=now)
    ).update(state="held", lease_token=None, lease_until=None,
             last_error="Retry budget exhausted, including expired workers", updated_at=now)
    changed = IngestionJob.objects.filter(pk=pk, attempts__lt=MAX_ATTEMPTS).filter(
        Q(state="pending", next_attempt_at__lte=now) | Q(state="running", lease_until__lte=now)
    ).update(state="running", lease_token=token, lease_until=now + LEASE_TIME,
             attempts=F("attempts") + 1, updated_at=now)
    if not changed:
        return None
    return token


def locked_job(pk, token):
    job = IngestionJob.objects.select_for_update().get(pk=pk)
    if job.state != "running" or job.lease_token != token or job.lease_until <= timezone.now():
        raise LostLease("Ingestion lease expired or replaced")
    return job


def archive(job, sources):
    for url, content in sources:
        IngestionSource.objects.get_or_create(
            job=job, url=url, sha256=hashlib.sha256(content).hexdigest(), defaults={"content": content})


def complete(job, outcome):
    job.state = "succeeded"
    job.outcome = outcome
    job.last_error = ""
    job.last_success_at = timezone.now()
    job.lease_token = None
    job.lease_until = None
    job.save()


def failed(pk, token, exc, sources):
    with transaction.atomic():
        job = locked_job(pk, token)
        archive(job, sources)
        job.state = "held" if job.attempts >= MAX_ATTEMPTS else "pending"
        job.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        delay = max(min(86400, 900 * 2 ** min(job.attempts - 1, 7)),
                    retry_after_seconds(getattr(exc, "response", None)))
        job.next_attempt_at = timezone.now() + timedelta(seconds=delay)
        job.lease_token = None
        job.lease_until = None
        job.save()


def run_pipeline(pipeline, start, end, **kwargs):
    # All EDGAR pipelines share one advisory lock to keep combined request rates
    # within the SEC limit. PostgreSQL releases this lock if the process dies.
    lock_key = 7042310901
    if connection.vendor != "postgresql":
        return _run_pipeline(pipeline, start, end, **kwargs)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [lock_key])
        if not cursor.fetchone()[0]:
            raise RuntimeError("Another EDGAR ingestion worker is active")
    try:
        return _run_pipeline(pipeline, start, end, **kwargs)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_key])


def _run_pipeline(pipeline, start, end, *, retry_limit=100, filing_limit=2000):
    if start > end or retry_limit < 1 or filing_limit < 1:
        raise ValueError("Invalid ingestion range or work limit")
    run = IngestionRun.objects.create(dataset=pipeline.dataset, start_date=start, end_date=end)
    stats = dict(days=0, entries=0, parsed=0, upserted=0, errors=0, skipped=0, existing=0, metadata=0)
    original_client = pipeline.client
    try:
        # Re-fetch successful recent indexes to discover additions; never reset failures,
        # retry deadlines or active leases. Successful accessions are not re-imported.
        # Recover scheduler downtime beyond the requested lookback. Once enqueued,
        # every missing day survives future bounded runs until resolved.
        latest_index = IngestionJob.objects.filter(dataset=pipeline.dataset, kind="index",
            last_success_at__isnull=False, source_date__lte=end).aggregate(value=Max("source_date"))["value"]
        coverage_start = min(start, latest_index + timedelta(days=1)) if latest_index else start
        for day in iter_business_days(coverage_start, end):
            job, _ = IngestionJob.objects.get_or_create(dataset=pipeline.dataset, kind="index", key=str(day),
                                                        defaults={"source_date": day})
            IngestionJob.objects.filter(pk=job.pk, state="succeeded").update(
                state="pending", attempts=0, next_attempt_at=timezone.now())
        due = Q(state="pending", next_attempt_at__lte=timezone.now()) | Q(state="running", lease_until__lte=timezone.now())
        indexes = list(IngestionJob.objects.filter(due, dataset=pipeline.dataset, kind="index").order_by(
            "next_attempt_at", "pk").values_list("pk", flat=True)[:retry_limit])
        for pk in indexes:
            token = claim(pk)
            if not token:
                continue
            recorder = RecordingClient(original_client)
            pipeline.client = recorder
            try:
                job = IngestionJob.objects.get(pk=pk)
                entries = pipeline._fetch_day_index(job.source_date)
                with transaction.atomic():
                    job = locked_job(pk, token)
                    groups = defaultdict(list)
                    for entry in entries:
                        candidate = asdict(entry)
                        group = groups[accession_from_filename(entry.filename)]
                        if candidate not in group:
                            group.append(candidate)
                    existing_ciks = dict(pipeline.filing_model.objects.filter(
                        accession_number__in=groups).values_list("accession_number", "issuer__cik"))
                    for accession, candidates in groups.items():
                        selected = next((entry for entry in candidates if entry["cik"].lstrip("0") ==
                                         existing_ciks.get(accession, "").lstrip("0")), candidates[0])
                        payload = {**selected, "index_candidates": candidates}
                        queued, created = IngestionJob.objects.get_or_create(
                            dataset=pipeline.dataset, kind="filing", key=accession,
                            defaults={"source_date": date.fromisoformat(selected["filing_date"]), "entry": payload})
                        if not created:
                            primary = {k: v for k, v in queued.entry.items() if k != "index_candidates"}
                            if primary not in candidates:
                                # Isolate an actual correction to its accession. Do
                                # not discard all other discoveries from this day.
                                queued.state = "held"
                                queued.last_error = "SEC index metadata changed; review required"
                                queued.save(update_fields=["state", "last_error", "updated_at"])
                                stats["errors"] += 1
                            else:
                                observed = queued.entry.get("index_candidates", [primary])
                                observed += [entry for entry in candidates if entry not in observed]
                                queued.entry = {**primary, "index_candidates": observed}
                                queued.save(update_fields=["entry", "updated_at"])
                    archive(job, recorder.sources)
                    job.discovered_count = len(entries)
                    complete(job, "indexed")
                stats["days"] += 1
                stats["entries"] += len(entries)
            except LostLease:
                stats["errors"] += 1
            except Exception as exc:
                response = getattr(exc, "response", None)
                if response is not None and response.status_code == 404 and expected_closure(job.source_date):
                    with transaction.atomic():
                        job = locked_job(pk, token)
                        complete(job, "scheduled_closure")
                    stats["days"] += 1
                else:
                    failed(pk, token, exc, recorder.sources)
                    stats["errors"] += 1
                    log.exception("Index ingestion failed: %s", job.key)
        # Old due work is included even when its date is outside the lookback.
        due = Q(state="pending", next_attempt_at__lte=timezone.now()) | Q(state="running", lease_until__lte=timezone.now())
        pending = list(IngestionJob.objects.filter(due, dataset=pipeline.dataset, kind="filing").order_by(
            "next_attempt_at", "pk").values_list("pk", flat=True)[:filing_limit])
        for pk in pending:
            token = claim(pk)
            if not token:
                continue
            recorder = RecordingClient(original_client)
            pipeline.client = recorder
            try:
                job = IngestionJob.objects.get(pk=pk)
                primary = {k: v for k, v in job.entry.items() if k != "index_candidates"}
                candidates = job.entry.get("index_candidates", [primary])
                entry = IndexEntry(**primary)
                # Existing data (including reviewed historical repairs) is immutable
                # under routine discovery. Explicit repair tools remain separate.
                existing = pipeline.filing_model.objects.filter(accession_number=job.key).select_related("issuer").first()
                parsed = None
                if not existing:
                    try:
                        parsed = pipeline._fetch_and_parse(entry)
                    except SourceCIKMismatch as exc:
                        # Co-issuers share an accession. Only an explicit source
                        # CIK present in the index can select a different entry.
                        matched = next((candidate for candidate in candidates
                                        if candidate["cik"].lstrip("0") == exc.source_cik), None)
                        if matched is None:
                            raise
                        entry = IndexEntry(**matched)
                        parsed = pipeline._fetch_and_parse(entry)
                if not existing and parsed is None:
                    raise ValueError("Parser returned no filing")
                with transaction.atomic():
                    job = locked_job(pk, token)
                    if existing:
                        if existing.issuer.cik.lstrip("0") != entry.cik.lstrip("0"):
                            raise ValueError("Existing filing/index CIK mismatch")
                        outcome = "existing"
                    else:
                        pipeline._upsert(parsed)
                        outcome = "metadata" if getattr(parsed, "metadata_only", False) else "structured"
                    job.entry = {**asdict(entry), "index_candidates": candidates}
                    archive(job, recorder.sources)
                    complete(job, outcome)
                stats["existing" if existing else "upserted"] += 1
                stats["parsed"] += int(not existing)
                stats["metadata"] += int(outcome == "metadata")
            except LostLease:
                stats["errors"] += 1
            except Exception as exc:
                failed(pk, token, exc, recorder.sources)
                stats["errors"] += 1
                log.exception("Failed to ingest accession %s", job.key)
        stats["backlog"] = IngestionJob.objects.filter(dataset=pipeline.dataset).exclude(state="succeeded").count()
        return stats
    except Exception:
        stats["errors"] += 1
        stats["fatal_error"] = True
        raise
    finally:
        pipeline.client = original_client
        run.stats = stats
        run.finished_at = timezone.now()
        run.save(update_fields=["stats", "finished_at"])
