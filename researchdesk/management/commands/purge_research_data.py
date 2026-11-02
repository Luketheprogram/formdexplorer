from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from researchdesk.models import ResearchJob, ReaderRequest


class Command(BaseCommand):
    help = "Expire generated download bytes after 24 hours and private feedback contact details after 90 days."

    def handle(self, *args, **opts):
        now = timezone.now()
        files = ResearchJob.objects.filter(
            kind="export",
            finished_at__lt=now - timedelta(hours=24),
            payload__isnull=False,
        ).update(payload=None)
        contacts = (
            ReaderRequest.objects.filter(created_at__lt=now - timedelta(days=90))
            .exclude(email="")
            .update(email="", consent_to_contact=False)
        )
        self.stdout.write(
            f"Expired files: {files}; expired feedback contact addresses: {contacts}."
        )
