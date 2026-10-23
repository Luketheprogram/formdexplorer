"""Read-only health checks: pipeline heartbeat, index coverage and unresolved work."""
from datetime import timedelta
from zoneinfo import ZoneInfo

from .calendar import expected_closure

from django.db.models import Count, Max, Q
from django.utils import timezone

from advisers.models import Adviser
from filings.models import IngestionJob, IngestionRun


def freshness_report(*, now=None, max_age_hours=36, backlog_age_hours=24):
    now = now or timezone.now()
    report = {"checked_at": now.isoformat(), "healthy": True, "datasets": {}}
    for dataset in ("d", "c", "a"):
        runs = IngestionRun.objects.filter(dataset=dataset).exclude(stats__has_key="operator_retry")
        latest = runs.order_by("-started_at", "-pk").first()
        completed = runs.filter(finished_at__isnull=False).aggregate(value=Max("finished_at"))["value"]
        jobs = IngestionJob.objects.filter(dataset=dataset)
        unresolved = jobs.exclude(state="succeeded")
        counts = dict(jobs.values_list("state").annotate(count=Count("pk")))
        index_date = jobs.filter(kind="index", last_success_at__isnull=False, outcome="indexed").aggregate(value=Max("source_date"))["value"]
        issues = []
        if not completed or now - completed > timedelta(hours=max_age_hours):
            issues.append("missing_or_stale_heartbeat")
        if latest and latest.finished_at is None and now - latest.started_at > timedelta(hours=max_age_hours):
            issues.append("unfinished_run")
        # Completion alone isn't success: recent failures/backlog remain visible.
        if latest and latest.stats.get("errors", 0):
            issues.append("latest_run_errors")
        if unresolved.filter(state="held").exists():
            issues.append("held_jobs")
        if unresolved.filter(created_at__lt=now - timedelta(hours=backlog_age_hours)).exists():
            issues.append("aged_backlog")
        if unresolved.filter(state="running", lease_until__lte=now).exists():
            issues.append("expired_leases")
        # Two publication days of tolerance, evaluated in SEC local time. A run
        # containing zero relevant filings still proves that its index was read.
        local_date = now.astimezone(ZoneInfo("America/New_York")).date()
        expected = local_date - timedelta(days=1)
        while expected_closure(expected):
            expected -= timedelta(days=1)
        previous = expected - timedelta(days=1)
        while expected_closure(previous):
            previous -= timedelta(days=1)
        if not index_date or index_date < previous:
            issues.append("stale_index_coverage")
        report["datasets"][dataset] = {
            "last_completed_at": completed.isoformat() if completed else None,
            "last_index_date": str(index_date) if index_date else None,
            "states": counts,
            "outcomes": dict(jobs.filter(kind="filing", state="succeeded").values_list("outcome").annotate(count=Count("pk"))),
            "issues": issues,
            "oldest_unresolved": unresolved.order_by("source_date").values("id", "kind", "key", "state", "last_error").first(),
        }
        report["healthy"] &= not issues
    # A recent adviser filing does not prove that the bulk import is complete.
    # Report the distinction rather than inventing an ADV pipeline heartbeat.
    adv = Adviser.objects.aggregate(latest_source_date=Max("last_filed_at"), latest_write_at=Max("updated_at"))
    report["adv"] = {k: v.isoformat() if v else None for k, v in adv.items()}
    report["adv"]["coverage_status"] = "refresh_not_instrumented"
    return report
