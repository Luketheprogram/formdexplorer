"""Chunked, checkpointed Form D backfill so a dropped SSH session only costs
one chunk, not the whole multi-year run."""

import json
import os
from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from filings.ingest.pipeline import IngestPipeline
from filings.ingest.health import has_ingestion_failures


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


class Command(BaseCommand):
    help = (
        "Backfill Form D filings in fixed-size day chunks with a JSON "
        "checkpoint file so interrupted runs can resume."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--start", type=str, required=True, help="YYYY-MM-DD (inclusive)"
        )
        parser.add_argument(
            "--end", type=str, required=True, help="YYYY-MM-DD (inclusive)"
        )
        parser.add_argument("--chunk-days", type=int, default=7)
        parser.add_argument(
            "--checkpoint",
            type=str,
            default="/tmp/form_d_backfill.json",
            help="JSON file tracking last completed chunk end-date",
        )
        parser.add_argument(
            "--resume", action="store_true", help="Start from checkpoint if present"
        )
        parser.add_argument("--no-raw-xml", action="store_true", default=False)

    def handle(self, *args, **opts):
        if not 1 <= opts["chunk_days"] <= 31:
            raise CommandError("--chunk-days must be between 1 and 31.")
        start = _parse(opts["start"])
        end = _parse(opts["end"])
        if end < start:
            raise CommandError("--end must be >= --start")

        cp_path = opts["checkpoint"]
        if opts["resume"] and os.path.exists(cp_path):
            with open(cp_path) as fh:
                saved = json.load(fh)
            resumed = _parse(saved["next_start"])
            if resumed > start:
                start = resumed
                self.stdout.write(self.style.WARNING(f"Resuming from {start}"))

        chunk = opts["chunk_days"]
        pipeline = IngestPipeline(store_raw_xml=not opts.get("no_raw_xml"))
        current = start
        while current <= end:
            chunk_end = min(current + timedelta(days=chunk - 1), end)
            self.stdout.write(f"Chunk {current} → {chunk_end}")
            stats = pipeline.run(current, chunk_end)
            self.stdout.write(f"  {stats}")
            if has_ingestion_failures(stats):
                raise CommandError(
                    "Ingestion remains incomplete. The checkpoint was not advanced; inspect the durable queue before resuming."
                )
            next_start = chunk_end + timedelta(days=1)
            temporary = cp_path + ".new"
            with open(temporary, "w") as fh:
                json.dump({"dataset": "d", "next_start": next_start.isoformat()}, fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temporary, cp_path)
            current = next_start
        self.stdout.write(
            self.style.SUCCESS(
                "Index discovery complete; inspect the durable filing queue for remaining work."
            )
        )
