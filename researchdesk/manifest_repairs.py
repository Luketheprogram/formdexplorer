"""Source-backed, insertion-only queue repair and guarded filing-date correction.

Financial values and issuer profiles are never overwritten. Missing historical
records enter the existing durable importer with alert suppression recorded.
"""

import csv
import hashlib
import io
import re
import zipfile

from django.db import transaction
from django.utils import timezone

from filings.models import Filing, IngestionJob, IngestionSource
from .models import ResearchJob
from .quarterly import parse_manifest


def details(payload):
    dates = parse_manifest(payload)  # Validates archive size, shape, and dates first.
    forms, issuers, ambiguous = {}, {}, set()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for table, required in [
            ("FORMDSUBMISSION", {"ACCESSIONNUMBER", "SUBMISSIONTYPE"}),
            (
                "ISSUERS",
                {"ACCESSIONNUMBER", "IS_PRIMARYISSUER_FLAG", "CIK", "ENTITYNAME"},
            ),
        ]:
            files = [
                f
                for f in archive.infolist()
                if f.filename.rsplit("/", 1)[-1].upper()
                in {table + ".TSV", table + ".TXT"}
            ]
            if len(files) != 1:
                raise ValueError("Exactly one source table is required: " + table)
            with archive.open(files[0]) as stream:
                reader = csv.DictReader(
                    io.TextIOWrapper(stream, encoding="utf-8-sig"), delimiter="\t"
                )
                if not required.issubset(reader.fieldnames or []):
                    raise ValueError("Unexpected source headers in " + table)
                for row in reader:
                    acc = row["ACCESSIONNUMBER"].strip()
                    if acc not in dates:
                        raise ValueError(
                            "Issuer table contains an unrecognized accession."
                        )
                    if table == "FORMDSUBMISSION":
                        forms[acc] = row["SUBMISSIONTYPE"].strip()
                    elif row["IS_PRIMARYISSUER_FLAG"].strip().upper() == "YES":
                        cik = row["CIK"].strip()
                        if not re.fullmatch(r"\d{1,10}", cik) or acc in issuers:
                            ambiguous.add(acc)
                        issuers[acc] = {
                            "cik": cik.lstrip("0") or "0",
                            "company": row["ENTITYNAME"].strip(),
                        }
    return dates, forms, issuers, ambiguous


def plan(payload, source_url, not_before, verified_dates=None):
    verified_dates = verified_dates or {}
    dates, forms, issuers, ambiguous = details(payload)
    existing = {
        f.accession_number: f
        for f in Filing.objects.filter(accession_number__in=dates)
        .select_related("issuer")
        .defer("raw_xml")
    }
    result = {
        "source_url": source_url,
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "not_before": str(not_before),
        "date_corrections": [],
        "date_disagreements": [],
        "metadata_corrections": [],
        "missing_to_queue": [],
        "held_for_review": [],
        "outside_scope": 0,
    }
    for acc, day in sorted(dates.items()):
        if day < not_before:
            result["outside_scope"] += 1
            continue
        primary = issuers.get(acc)
        if not primary or acc in ambiguous or not primary["company"]:
            result["held_for_review"].append(
                {
                    "accession": acc,
                    "reason": "Missing or ambiguous primary issuer metadata.",
                }
            )
            continue
        filing = existing.get(acc)
        entry = {
            "form_type": forms[acc],
            "company": primary["company"],
            "cik": primary["cik"],
            "filing_date": str(day),
            "filename": f'edgar/data/{int(primary["cik"])}/{acc}.txt',
            "historical_repair": True,
            "manifest_source": source_url,
        }
        if filing:
            if filing.issuer.cik.lstrip("0") != primary["cik"].lstrip("0"):
                result["held_for_review"].append(
                    {
                        "accession": acc,
                        "reason": "Stored issuer CIK differs from the primary source issuer.",
                    }
                )
            else:
                target_date = filing.filing_date
                if filing.filing_date != day:
                    verified = verified_dates.get(acc, {})
                    if verified.get("filing_date") == str(day):
                        target_date = day
                    else:
                        result["date_disagreements"].append(
                            {
                                "accession": acc,
                                "stored_date": str(filing.filing_date),
                                "quarterly_date": str(day),
                                "current_index_date": verified.get("filing_date"),
                                "reason": "Dates can be officially adjusted; no quarterly-only date overwrite.",
                            }
                        )
                if (
                    filing.filing_date != target_date
                    or filing.form_type != forms[acc]
                    or filing.is_amendment != (forms[acc] == "D/A")
                ):
                    change = {
                        "accession": acc,
                        "old_date": str(filing.filing_date),
                        "new_date": str(target_date),
                        "issuer_id": filing.issuer_id,
                        "old_form_type": filing.form_type,
                        "new_form_type": forms[acc],
                        "old_is_amendment": filing.is_amendment,
                        "new_is_amendment": forms[acc] == "D/A",
                    }
                    result["metadata_corrections"].append(change)
                    if filing.filing_date != target_date:
                        result["date_corrections"].append(change)
        else:
            result["missing_to_queue"].append({"accession": acc, "entry": entry})
    return result


@transaction.atomic
def apply(payload, source_url, not_before, verified_dates=None, enqueue_missing=True):
    from datetime import date

    result = plan(payload, source_url, not_before, verified_dates=verified_dates)
    dates, _, _, _ = details(payload)
    archive_job, _ = IngestionJob.objects.get_or_create(
        dataset="d",
        kind="quarter",
        key=source_url.rsplit("/", 1)[-1],
        defaults={
            "source_date": max(dates.values()),
            "state": "succeeded",
            "outcome": "manifest_checked",
        },
    )
    IngestionSource.objects.get_or_create(
        job=archive_job,
        url=source_url,
        sha256=result["source_sha256"],
        defaults={"content": payload},
    )
    changes = result["metadata_corrections"]
    for offset in range(0, len(changes), 500):
        batch = changes[offset : offset + 500]
        records = {
            f.accession_number: f
            for f in Filing.objects.select_for_update()
            .filter(accession_number__in=[r["accession"] for r in batch])
            .defer("raw_xml")
        }
        for change in batch:
            record = records.get(change["accession"])
            if (
                not record
                or record.issuer_id != change["issuer_id"]
                or str(record.filing_date) != change["old_date"]
                or record.form_type != change["old_form_type"]
                or record.is_amendment != change["old_is_amendment"]
            ):
                raise ValueError(
                    "A filing changed after planning; retry the source audit."
                )
            record.filing_date = date.fromisoformat(change["new_date"])
            record.form_type = change["new_form_type"]
            record.is_amendment = change["new_is_amendment"]
            record.updated_at = timezone.now()
        Filing.objects.bulk_update(
            list(records.values()),
            ["filing_date", "form_type", "is_amendment", "updated_at"],
            batch_size=500,
        )
    queued = []
    for item in result["missing_to_queue"] if enqueue_missing else []:
        entry = item["entry"]
        job, created = IngestionJob.objects.get_or_create(
            dataset="d",
            kind="filing",
            key=item["accession"],
            defaults={
                "source_date": date.fromisoformat(entry["filing_date"]),
                "entry": entry,
            },
        )
        if not created:
            # Preserve holds, leases, source candidates and retry budgets. The
            # historical marker prevents surprise backfill notification emails.
            job.entry = {**job.entry, "historical_repair": True}
            job.save(update_fields=["entry", "updated_at"])
        queued.append(job.pk)
    result["queued_job_ids"] = queued
    result["missing_enqueued"] = enqueue_missing
    result["date_index_checks"] = [
        {k: v for k, v in check.items() if k != "content"}
        for check in (verified_dates or {}).values()
    ]
    for check in (verified_dates or {}).values():
        if check.get("accepted_at"):
            metadata, _ = IngestionJob.objects.update_or_create(
                dataset="d",
                kind="metadata",
                key=check["accession"],
                defaults={
                    "source_date": date.fromisoformat(check["filing_date"]),
                    "entry": {k: v for k, v in check.items() if k != "content"},
                    "state": "succeeded",
                    "outcome": "index_verified",
                },
            )
            if "content" in check:
                IngestionSource.objects.get_or_create(
                    job=metadata,
                    url=check["source_url"],
                    sha256=check["source_sha256"],
                    defaults={"content": check["content"]},
                )
        if "content" in check:
            IngestionSource.objects.get_or_create(
                job=archive_job,
                url=check["source_url"],
                sha256=check["source_sha256"],
                defaults={"content": check["content"]},
            )
    result["applied_at"] = timezone.now().isoformat()
    ResearchJob.objects.create(
        kind="metadata-correction",
        state="finished",
        params=result,
        finished_at=timezone.now(),
    )
    return result


def verify_date_indexes(payload, client):
    from lxml import html
    from datetime import date

    dates, _, issuers, ambiguous = details(payload)
    result = {}
    for record in (
        Filing.objects.filter(accession_number__in=dates)
        .select_related("issuer")
        .defer("raw_xml")
    ):
        acc = record.accession_number
        if (
            record.filing_date == dates[acc]
            or acc in ambiguous
            or not issuers.get(acc)
            or record.issuer.cik.lstrip("0") != issuers[acc]["cik"].lstrip("0")
        ):
            continue
        content = client.get_bytes(record.edgar_url)
        if acc not in content.decode("utf-8", errors="replace"):
            raise ValueError(
                "Accession absent from source index; no date verification."
            )
        doc = html.fromstring(content)
        values = doc.xpath(
            '//div[contains(@class,"infoHead") and normalize-space()="Filing Date"]/following-sibling::div[@class="info"][1]/text()'
        )
        if len(values) != 1:
            raise ValueError("Ambiguous SEC filing-date field; no date verification.")
        filed = date.fromisoformat(values[0].strip())
        from datetime import datetime
        from zoneinfo import ZoneInfo

        accepted = doc.xpath(
            '//div[contains(@class,"infoHead") and normalize-space()="Accepted"]/following-sibling::div[@class="info"][1]/text()'
        )
        accepted_at = (
            datetime.strptime(accepted[0].strip(), "%Y-%m-%d %H:%M:%S")
            .replace(tzinfo=ZoneInfo("America/New_York"))
            .isoformat()
            if len(accepted) == 1
            else None
        )
        result[acc] = {
            "accession": acc,
            "accepted_at": accepted_at,
            "filing_date": str(filed),
            "source_url": record.edgar_url,
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "content": content,
        }
    return result
