"""A finite cron worker: exports, extraction, reconciliation and retention."""

from datetime import date

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from researchdesk.analysis import period
from researchdesk.jobs import run, extraction_queryset
from researchdesk.models import ResearchEdition, ResearchJob
from filings.models import IngestionJob


class Command(BaseCommand):
    help = "Run one bounded research maintenance cycle, then exit. No email or automatic publication."

    def handle(self, *args, **options):
        # A separate maintenance lock allows ingest to continue. Only explicit
        # source-recovery tasks acquire the global SEC network-request lock.
        lock_key = 7042310903
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [lock_key])
                if not cursor.fetchone()[0]:
                    self.stdout.write(
                        "A research maintenance cycle is already running."
                    )
                    return
        import uuid

        key = uuid.uuid5(
            uuid.NAMESPACE_URL, "formd-maintenance:" + str(timezone.localdate())
        )
        pulse = None
        try:
            pulse, _ = ResearchJob.objects.update_or_create(
                request_key=key,
                defaults={
                    "kind": "maintenance-heartbeat",
                    "state": "running",
                    "params": {"started_at": timezone.now().isoformat()},
                    "finished_at": None,
                },
            )
            due = Q(state="pending") | Q(
                state="running", lease_until__lte=timezone.now()
            )
            ids = list(
                ResearchJob.objects.filter(due)
                .order_by("created_at")
                .values_list("pk", flat=True)[:20]
            )
            for pk in ids:
                run(pk)
            historical_due = Q(
                state="pending", next_attempt_at__lte=timezone.now()
            ) | Q(state="running", lease_until__lte=timezone.now())
            if IngestionJob.objects.filter(
                historical_due,
                dataset="d",
                kind="filing",
                entry__historical_repair=True,
            ).exists():
                job = ResearchJob.objects.create(kind="historical-ingestion", params={})
                run(job.pk)
            for dataset in ("d", "c", "a"):
                if not extraction_queryset(dataset).exists():
                    continue
                job = ResearchJob.objects.create(
                    kind="extract", params={"dataset": dataset}
                )
                run(job.pk)
            # Reconcile each dataset once daily, not on every five-minute tick.
            today = timezone.localdate()
            for dataset in ("d", "c", "a"):
                already = ResearchJob.objects.filter(
                    kind="reconcile",
                    state="finished",
                    params__dataset=dataset,
                    created_at__date=today,
                ).exists()
                if not already:
                    job = ResearchJob.objects.create(
                        kind="reconcile", params={"dataset": dataset, "days": 90}
                    )
                    run(job.pk)
            start, end = period({})
            if not ResearchEdition.objects.filter(
                series="monthly-disclosures", period_start=start, period_end=end
            ).exists():
                job = ResearchJob.objects.create(kind="monthly-draft", params={})
                run(job.pk)
            call_command("purge_research_data", stdout=self.stdout)
            ResearchJob.objects.filter(pk=pulse.pk).update(
                state="finished", finished_at=timezone.now(), error=""
            )
            self.stdout.write(
                "Research maintenance finished. No publication or email was sent."
            )
        except Exception as exc:
            if pulse is not None:
                ResearchJob.objects.filter(pk=pulse.pk).update(
                    state="failed", finished_at=timezone.now(), error=type(exc).__name__
                )
            raise
        finally:
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_key])
