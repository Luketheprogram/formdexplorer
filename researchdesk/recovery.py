"""Operator-only, bounded recovery of missing primary sources.

Recovery never changes issuer identity or financial fields. The original response
bytes are archived, including failed or unsupported documents, for review.
"""

import re
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone
from lxml import etree

from filings.ingest.edgar_client import EdgarClient
from filings.ingest.index_parser import IndexEntry
from filings.ingest.models import IngestionJob
from filings.ingest.reliability import RecordingClient, archive
from rega.ingest.documents import primary_document, validate_xml
from .evidence import MODELS, materialize


def recover(dataset, limit=5, client=None):
    if dataset not in MODELS or not 1 <= limit <= 25:
        raise ValueError(
            "Choose a supported dataset and a batch of at most 25 sources."
        )
    lock_key = (
        7042310901  # The same global SEC request lock as every ingestion pipeline.
    )
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [lock_key])
            if not cursor.fetchone()[0]:
                raise RuntimeError(
                    "An SEC ingestion worker is active; retry recovery later."
                )
    network = client or EdgarClient(rate_per_sec=4)
    completed = 0
    try:
        held = IngestionJob.objects.filter(
            dataset=dataset, kind="recovery", state="held"
        ).values("key")
        records = (
            MODELS[dataset]
            .objects.filter(raw_xml="")
            .exclude(accession_number__in=held)
            .select_related("issuer")
            .order_by("-filing_date", "-pk")[:limit]
        )
        for item in records:
            if (
                not re.fullmatch(r"\d{10}-\d{2}-\d{6}", item.accession_number)
                or not item.issuer.cik.isdigit()
            ):
                continue
            job, _ = IngestionJob.objects.get_or_create(
                dataset=dataset,
                kind="recovery",
                key=item.accession_number,
                defaults={"source_date": item.filing_date},
            )
            if job.state == "held":
                continue
            recording = RecordingClient(network)
            job.state = "running"
            job.attempts += 1
            job.save()
            try:
                entry = IndexEntry(
                    form_type=item.form_type,
                    company=item.issuer.name,
                    cik=item.issuer.cik,
                    filing_date=str(item.filing_date),
                    filename=f"edgar/data/{int(item.issuer.cik)}/{item.accession_number}.txt",
                )
                document = primary_document(recording, entry)
                if len(document.content) > 5_000_000 or not document.structured:
                    raise ValueError(
                        "Source is unstructured or exceeds extraction limits; retained for review."
                    )
                validate_xml(document.content, expected_form=item.form_type)
                root = etree.fromstring(
                    document.content,
                    etree.XMLParser(resolve_entities=False, no_network=True),
                )
                issuer_nodes = root.xpath(
                    ".//*[local-name()='primaryIssuer' or local-name()='issuerInformation' or local-name()='issuerInfo']"
                )
                ciks = {
                    value.strip().lstrip("0")
                    for node in issuer_nodes
                    for value in node.xpath(
                        ".//*[local-name()='cik' or local-name()='issuerCik']/text()"
                    )
                }
                if ciks != {item.issuer.cik.lstrip("0")}:
                    raise ValueError(
                        "Primary source issuer CIK is absent or disagrees; no record changed."
                    )
                with transaction.atomic():
                    archive(job, recording.sources)
                    updated = (
                        MODELS[dataset]
                        .objects.filter(pk=item.pk, raw_xml="")
                        .update(
                            raw_xml=document.content.decode("utf-8-sig"),
                            updated_at=timezone.now(),
                        )
                    )
                    if updated:
                        item.refresh_from_db()
                        materialize(dataset, item)
                        completed += 1
                    job.state = "succeeded"
                    job.outcome = "source_recovered"
                    job.last_success_at = timezone.now()
                    job.last_error = ""
                    job.save()
            except Exception as exc:
                archive(job, recording.sources)
                job.state = "held"
                job.last_error = f"{type(exc).__name__}: {exc}"[:1000]
                job.save()
    finally:
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_key])
    return completed
