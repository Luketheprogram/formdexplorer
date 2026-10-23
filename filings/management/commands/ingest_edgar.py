"""Run every dataset even if another fails; one shared SEC client/rate limiter."""
import json
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from crowdfunding.ingest.pipeline import FormCPipeline
from filings.ingest.edgar_client import EdgarClient
from filings.ingest.pipeline import IngestPipeline
from rega.ingest.pipeline import Form1APipeline


class Command(BaseCommand):
    help = "Ingest published daily indexes and retry durable backlog for D, C and Reg A."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--filing-limit", type=int, default=2000)
        parser.add_argument("--retry-limit", type=int, default=100)

    def handle(self, *args, **opts):
        if not 1 <= opts["days"] <= 366 or min(opts["filing_limit"], opts["retry_limit"]) < 1:
            raise CommandError("Use 1–366 days and positive work limits")
        # SEC daily indexes are published overnight, not an intraday feed.
        end = timezone.now().astimezone(ZoneInfo("America/New_York")).date() - timedelta(days=1)
        start = end - timedelta(days=opts["days"] - 1)
        client = EdgarClient()
        results = {}
        for pipeline in (IngestPipeline, FormCPipeline, Form1APipeline):
            try:
                results[pipeline.dataset] = pipeline(client=client).run(
                    start, end, filing_limit=opts["filing_limit"], retry_limit=opts["retry_limit"])
            except Exception as exc:
                results[pipeline.dataset] = {"errors": 1, "error": f"{type(exc).__name__}: {exc}"}
        self.stdout.write(json.dumps(results, sort_keys=True))
        if any(result.get("errors") or result.get("backlog") for result in results.values()):
            raise CommandError("Ingestion has unresolved work; all datasets were attempted")
