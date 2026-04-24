from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from filings.ingest.pipeline import IngestPipeline


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


class Command(BaseCommand):
    help = "Ingest Form D / D/A filings from EDGAR daily indexes."

    def add_arguments(self, parser):
        parser.add_argument("--start", type=str, help="YYYY-MM-DD (inclusive)")
        parser.add_argument("--end", type=str, help="YYYY-MM-DD (inclusive)")
        parser.add_argument("--days", type=int, help="Last N days ending today (mutually exclusive with --start/--end)")
        parser.add_argument("--no-raw-xml", action="store_true", help="Do not store raw_xml on Filing")

    def handle(self, *args, **opts):
        if opts.get("days"):
            end = date.today()
            start = end - timedelta(days=opts["days"] - 1)
        else:
            if not opts.get("start") or not opts.get("end"):
                raise CommandError("Provide --days N, or both --start and --end.")
            start = _parse(opts["start"])
            end = _parse(opts["end"])
        if end < start:
            raise CommandError("--end must be >= --start")

        self.stdout.write(f"Ingesting {start} -> {end}")
        pipeline = IngestPipeline(store_raw_xml=not opts.get("no_raw_xml"))
        stats = pipeline.run(start, end)
        self.stdout.write(self.style.SUCCESS(f"Done: {stats}"))
