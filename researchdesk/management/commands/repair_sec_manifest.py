import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError

from researchdesk.manifest_repairs import plan, apply, verify_date_indexes


class Command(BaseCommand):
    help = "Preview source-backed filing-date corrections and missing-accession queue repairs. Never overwrites financial values or issuer profiles."

    def add_arguments(self, parser):
        parser.add_argument("--archive", required=True)
        parser.add_argument("--source-url", required=True)
        parser.add_argument("--not-before", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--verify-date-indexes", action="store_true")
        parser.add_argument(
            "--metadata-only",
            action="store_true",
            help="Do not enqueue missing records",
        )

    def handle(self, *args, **options):
        import re

        url = urlsplit(options["source_url"])
        if (
            url.scheme != "https"
            or url.netloc != "www.sec.gov"
            or not re.fullmatch(r"\d{4}q[1-4]_d\.zip", url.path.rsplit("/", 1)[-1])
            or url.query
            or url.fragment
        ):
            raise CommandError("Provide the exact SEC HTTPS quarterly archive URL.")
        try:
            start = date.fromisoformat(options["not_before"])
            path = Path(options["archive"])
            if path.stat().st_size > 20 * 1024 * 1024:
                raise ValueError("Source archive exceeds 20 MiB.")
            payload = path.read_bytes()
            checks = {}
            if options["verify_date_indexes"]:
                from filings.ingest.edgar_client import EdgarClient

                checks = verify_date_indexes(payload, EdgarClient(rate_per_sec=2))
            if options["apply"]:
                result = apply(
                    payload,
                    options["source_url"],
                    start,
                    verified_dates=checks,
                    enqueue_missing=not options["metadata_only"],
                )
            else:
                result = plan(
                    payload, options["source_url"], start, verified_dates=checks
                )
            Path(options["output"]).write_text(json.dumps(result, indent=2) + "\n")
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f'{"Applied" if options["apply"] else "Preview"}: {len(result["metadata_corrections"])} metadata records, {len(result["date_corrections"])} filing dates, {len(result["missing_to_queue"])} missing records, {len(result["held_for_review"])} held. No financial or issuer fields changed; no email sent.'
        )
