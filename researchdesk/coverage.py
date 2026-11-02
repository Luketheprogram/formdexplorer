"""Reconcile exact accessions against immutable retrieved SEC index bytes."""

from collections import defaultdict
from datetime import timedelta, date
from django.utils import timezone
from filings.ingest.calendar import expected_closure
from filings.models import IngestionJob
from .evidence import MODELS
from .models import CoverageDay

FORM_TYPES = {
    "d": {"D", "D/A"},
    "c": {x[0] for x in MODELS["c"].FORM_TYPES},
    "a": {x[0] for x in MODELS["a"].FORM_TYPES},
}


def publication_days_since(day, *, today=None):
    today = (
        today
        or timezone.now()
        .astimezone(__import__("zoneinfo").ZoneInfo("America/New_York"))
        .date()
    )
    # Bound old histories without an unbounded day-by-day loop.
    if not day:
        return None
    elapsed = 0
    for offset in range(1, min((today - day).days, 3660) + 1):
        if not expected_closure(day + timedelta(days=offset)):
            elapsed += 1
    return elapsed


def reconcile_day(dataset, day):
    job = IngestionJob.objects.filter(
        dataset=dataset, kind="index", source_date=day
    ).first()
    sources = list(job.sources.order_by("-retrieved_at")[:1]) if job else []
    stored = set(
        MODELS[dataset]
        .objects.filter(filing_date=day)
        .values_list("accession_number", flat=True)
    )
    data = {
        "stored": len(stored),
        "expected": None,
        "missing": [],
        "unexpected": [],
        "status": "unchecked",
        "checked_at": timezone.now(),
        "notes": "No successfully retrieved SEC index is available for comparison.",
        "source_url": "",
        "source_hash": "",
    }
    if sources:
        source = sources[0]
        content = bytes(source.content).decode("utf-8", errors="replace")
        expected = set()
        malformed = False
        try:
            from filings.ingest.index_parser import (
                accession_from_filename,
                parse_form_idx,
            )
            import re

            if "CIK|Company Name|Form Type|Date Filed|Filename" in content:
                rows = []
                for line in content.splitlines():
                    if not line.strip() or line.startswith(("CIK|", "---")):
                        continue
                    pieces = line.split("|")
                    if len(pieces) != 5:
                        raise ValueError("Malformed master index row")
                    if pieces[2].strip() in FORM_TYPES[dataset]:
                        rows.append((pieces[3].strip(), pieces[4].strip()))
            else:
                rows = [
                    (entry.filing_date, entry.filename)
                    for entry in parse_form_idx(
                        content, form_types=tuple(FORM_TYPES[dataset]), strict=True
                    )
                ]
            for filed, filename in rows:
                accession = accession_from_filename(filename)
                if date.fromisoformat(
                    filed
                    if "-" in filed
                    else filed[:4] + "-" + filed[4:6] + "-" + filed[6:]
                ) > day or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
                    raise ValueError("Invalid accession or index date")
                expected.add(accession)
            # An index publication day may contain officially adjusted earlier
            # filing dates. Check expected accessions globally, not by date.
            stored = set(
                MODELS[dataset]
                .objects.filter(accession_number__in=expected)
                .values_list("accession_number", flat=True)
            )
            missing = sorted(expected - stored)
            unexpected = []
            data.update(
                expected=len(expected),
                stored=len(stored),
                missing=missing,
                unexpected=unexpected,
                status="complete" if not missing and not unexpected else "partial",
                source_url=source.url,
                source_hash=source.sha256,
                notes="Exact accession membership comparison with this published SEC index. Official filing dates can be adjusted and differ from publication dates. Completeness applies only to this index and form-type scope.",
            )
        except (ValueError, TypeError, IndexError):
            data.update(
                status="failed",
                source_url=source.url,
                source_hash=source.sha256,
                notes="Stored index could not be validated; no completeness claim made.",
            )
    elif (
        job
        and job.state == "succeeded"
        and job.outcome in {"expected_closure", "closed", "scheduled_closure"}
        and expected_closure(day)
    ):
        data.update(
            status="closed",
            notes="Expected SEC closure; no published index was retrieved. No market-activity claim.",
        )
    elif job and job.state in {"failed", "held"}:
        data.update(status="failed", notes="Index retrieval or review is unresolved.")
    return CoverageDay.objects.update_or_create(
        dataset=dataset, day=day, defaults=data
    )[0]


def calendar_rows(dataset, *, days=90):
    today = (
        timezone.now()
        .astimezone(__import__("zoneinfo").ZoneInfo("America/New_York"))
        .date()
    )
    start = today - timedelta(days=days - 1)
    existing = {
        r.day: r
        for r in CoverageDay.objects.filter(
            dataset=dataset, day__gte=start, day__lte=today
        )
    }
    return [
        {
            "day": start + timedelta(days=i),
            "check": existing.get(start + timedelta(days=i)),
            "closed": expected_closure(start + timedelta(days=i)),
        }
        for i in range(days)
    ]
