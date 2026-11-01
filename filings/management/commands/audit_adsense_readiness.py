import json

from django.core.management.base import BaseCommand

from filings.readiness import readiness_audit


class Command(BaseCommand):
    help = "Read-only local AdSense readiness audit; never submits a review or enables advertising."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(readiness_audit(), indent=2))
