import json

from django.core.management.base import BaseCommand

from filings.readiness import quality_audit


class Command(BaseCommand):
    help = "Read-only route and stored-content quality audit; does not alter indexing or publish content."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(quality_audit(), indent=2))
