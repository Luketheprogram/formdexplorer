from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone
from researchdesk.models import ResearchJob
from researchdesk.jobs import run


class Command(BaseCommand):
    help = "Process bounded queued research work; never sends email or enables ads."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=5)

    def handle(self, *args, **opts):
        if not 1 <= opts["limit"] <= 100:
            raise CommandError("Use a limit between 1 and 100.")
        ids = list(
            ResearchJob.objects.filter(
                Q(state="pending") | Q(state="running", lease_until__lte=timezone.now())
            )
            .order_by("created_at")
            .values_list("pk", flat=True)[: opts["limit"]]
        )
        for pk in ids:
            self.stdout.write(f'{pk}: {"finished" if run(pk) else "not completed"}')
