from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from crowdfunding.ingest.pipeline import FormCPipeline


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


class Command(BaseCommand):
    help = "Ingest Form C / C-* filings from EDGAR daily indexes."

    def add_arguments(self, parser):
        parser.add_argument("--start", type=str)
        parser.add_argument("--end", type=str)
        parser.add_argument("--days", type=int)
        parser.add_argument("--no-raw-xml", action="store_true")

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

        self.stdout.write(f"Ingesting Form C: {start} -> {end}")
        pipeline = FormCPipeline(store_raw_xml=not opts.get("no_raw_xml"))
        stats = pipeline.run(start, end)
        self.stdout.write(self.style.SUCCESS(f"Done: {stats}"))
