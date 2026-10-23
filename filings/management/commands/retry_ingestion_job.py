from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from filings.models import IngestionJob


class Command(BaseCommand):
    help = "Explicitly requeue one held job after investigation; retains sources and requires a note."

    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)
        parser.add_argument("--note", required=True)

    @transaction.atomic
    def handle(self, *args, **opts):
        if not opts["note"].strip():
            raise CommandError("A review note is required")
        job = IngestionJob.objects.select_for_update().filter(pk=opts["job_id"]).first()
        if not job or job.state != "held":
            raise CommandError("Only a held job can be requeued")
        from filings.models import IngestionRun
        IngestionRun.objects.create(dataset=job.dataset, start_date=job.source_date, end_date=job.source_date,
            stats={"operator_retry": job.pk, "note": opts["note"], "previous_attempts": job.attempts,
                   "previous_error": job.last_error})
        job.state = "pending"
        job.attempts = 0
        job.next_attempt_at = timezone.now()
        job.save()
        self.stdout.write(f"Requeued {job.pk}; source documents retained")
