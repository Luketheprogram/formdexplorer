"""Chunked, checkpointed Form 1-A backfill with a hard floor of 2023-01-01."""

import json
import os
from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from rega.ingest.pipeline import Form1APipeline

HARD_FLOOR = date(2023, 1, 1)


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


class Command(BaseCommand):
    help = "Backfill Form 1-A filings in fixed-size day chunks. Will not go before 2023-01-01."

    def add_arguments(self, parser):
        parser.add_argument("--start", type=str, default="2023-01-01")
        parser.add_argument("--end", type=str, required=True)
        parser.add_argument("--chunk-days", type=int, default=14)
        parser.add_argument("--checkpoint", type=str, default="/tmp/form_1a_backfill.json")
        parser.add_argument("--resume", action="store_true")
        parser.add_argument("--no-raw-xml", action="store_true", default=True)

    def handle(self, *args, **opts):
        start = max(_parse(opts["start"]), HARD_FLOOR)
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
        pipeline = Form1APipeline(store_raw_xml=not opts.get("no_raw_xml"))
        current = start
        while current <= end:
            chunk_end = min(current + timedelta(days=chunk - 1), end)
            self.stdout.write(f"Chunk {current} → {chunk_end}")
            stats = pipeline.run(current, chunk_end)
            self.stdout.write(f"  {stats}")
            next_start = chunk_end + timedelta(days=1)
            with open(cp_path, "w") as fh:
                json.dump({"next_start": next_start.isoformat()}, fh)
            current = next_start
        self.stdout.write(self.style.SUCCESS("Backfill complete."))
