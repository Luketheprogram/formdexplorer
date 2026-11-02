from django.core.management.base import BaseCommand, CommandError
from researchdesk.models import ResearchJob
from researchdesk.jobs import run


class Command(BaseCommand):
    help = "Extract a bounded source batch, reconcile stored indexes, or prepare an unpublished monthly draft."

    def add_arguments(self, parser):
        parser.add_argument(
            "operation", choices=["extract", "reconcile", "monthly-draft", "recover"]
        )
        parser.add_argument("--dataset", choices=["d", "c", "a"], default="d")

    def handle(self, *args, **opts):
        job = ResearchJob.objects.create(
            kind=opts["operation"], params={"dataset": opts["dataset"]}
        )
        if not run(job.pk):
            job.refresh_from_db()
            raise CommandError(job.error or "Job was not claimed.")
        self.stdout.write(
            f"Completed {job.kind} job {job.pk}; no research was published."
        )
