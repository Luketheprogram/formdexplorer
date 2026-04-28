"""Re-fetch primary_doc.xml for Form D filings that don't yet have banker_count
populated, parse just the recipientList, and update the row.

Necessary because earlier ingest runs were called with --no-raw-xml and the
old XML parser looked at element names that don't exist, so every existing
filing has banker_count=NULL. This walks the gap."""

import logging
from datetime import date

from django.core.management.base import BaseCommand
from django.db import OperationalError, connection

from filings.ingest.edgar_client import EdgarClient
from filings.ingest.index_parser import primary_doc_url
from filings.ingest.xml_parser import parse_primary_doc
from filings.models import Filing

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill banker_count + banker_names for Filings missing the data."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Stop after N filings (0 = no cap)")
        parser.add_argument("--start", type=str, default="", help="Only filings on or after YYYY-MM-DD")

    def handle(self, *args, **opts):
        client = EdgarClient()
        qs = Filing.objects.filter(banker_count__isnull=True).select_related("issuer").order_by("-filing_date")
        if opts.get("start"):
            qs = qs.filter(filing_date__gte=opts["start"])
        if opts.get("limit"):
            qs = qs[: opts["limit"]]

        total = qs.count() if opts.get("limit") == 0 else opts["limit"]
        self.stdout.write(f"Backfilling banker info for ~{total} filings")
        done = 0
        skipped = 0
        for filing in qs.iterator():
            cik = filing.issuer.cik
            acc_no_dashes = filing.accession_number.replace("-", "")
            url = f"/Archives/edgar/data/{int(cik)}/{acc_no_dashes}/primary_doc.xml"
            try:
                xml_bytes = client.get_bytes(url)
            except Exception as exc:  # noqa: BLE001
                log.warning("fetch failed for %s: %s", filing.accession_number, exc)
                skipped += 1
                continue
            try:
                parsed = parse_primary_doc(xml_bytes, filing.accession_number)
            except Exception as exc:  # noqa: BLE001
                log.warning("parse failed for %s: %s", filing.accession_number, exc)
                skipped += 1
                continue
            try:
                Filing.objects.filter(pk=filing.pk).update(
                    banker_count=parsed.banker_count if parsed.banker_count is not None else 0,
                    banker_names=parsed.banker_names,
                )
            except OperationalError as exc:
                log.warning("DB drop, reconnecting: %s", exc)
                connection.close()
                Filing.objects.filter(pk=filing.pk).update(
                    banker_count=parsed.banker_count if parsed.banker_count is not None else 0,
                    banker_names=parsed.banker_names,
                )
            done += 1
            if done % 200 == 0:
                self.stdout.write(f"  {done} done, {skipped} skipped")
        self.stdout.write(self.style.SUCCESS(f"Done: {done} updated, {skipped} skipped"))
