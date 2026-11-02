import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from researchdesk.quarterly import compare_manifest


class Command(BaseCommand):
    help = "Read-only comparison with an exact downloaded SEC quarterly Form D archive."

    def add_arguments(self, parser):
        parser.add_argument("--archive", required=True)
        parser.add_argument("--year", required=True, type=int)
        parser.add_argument("--quarter", required=True, type=int, choices=range(1, 5))
        parser.add_argument(
            "--source-url",
            required=True,
            help="Exact HTTPS SEC download URL for this archive",
        )
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        if not 2008 <= options["year"] <= 2100:
            raise CommandError("Invalid SEC posting year.")
        from urllib.parse import urlsplit

        source = options["source_url"]
        parsed = urlsplit(source)
        expected = f"{options['year']}q{options['quarter']}_d.zip"
        if (
            parsed.scheme != "https"
            or parsed.netloc != "www.sec.gov"
            or parsed.path.rsplit("/", 1)[-1] != expected
            or parsed.query
            or parsed.fragment
        ):
            raise CommandError(
                "Provide the exact SEC HTTPS archive URL matching the selected year and quarter."
            )

        try:
            path = Path(options["archive"])
            if path.stat().st_size > 20 * 1024 * 1024:
                raise ValueError("Archive exceeds 20 MiB.")
            report = compare_manifest(path.read_bytes(), source)
            Path(options["output"]).write_text(json.dumps(report, indent=2) + "\n")
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"Compared {report['expected']} accessions: {report['matched']} stored; {len(report['missing'])} missing. Report: {options['output']}"
        )
