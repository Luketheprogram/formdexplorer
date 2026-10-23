import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from filings.ingest.monitoring import freshness_report


class Command(BaseCommand):
    help = "Read-only ingestion health JSON; nonzero exit on missing, stale or failed EDGAR ingestion."

    def add_arguments(self, parser):
        parser.add_argument("--max-age-hours", type=int, default=36)
        parser.add_argument("--backlog-age-hours", type=int, default=24)
        parser.add_argument("--report-sentry", action="store_true")
        parser.add_argument("--notification-test", action="store_true",
                            help="Exit with a clearly labeled test failure without querying or changing data")

    def handle(self, *args, **opts):
        if opts["notification_test"] or os.environ.get("INGESTION_NOTIFICATION_TEST") == "1":
            raise CommandError("NOTIFICATION TEST ONLY: intentional freshness-monitor failure; no data queried or changed")
        if min(opts["max_age_hours"], opts["backlog_age_hours"]) < 1:
            raise CommandError("Health thresholds must be positive")
        report = freshness_report(max_age_hours=opts["max_age_hours"], backlog_age_hours=opts["backlog_age_hours"])
        self.stdout.write(json.dumps(report, sort_keys=True))
        if not report["healthy"]:
            if opts["report_sentry"] and settings.SENTRY_DSN:
                import sentry_sdk
                with sentry_sdk.push_scope() as scope:
                    scope.fingerprint = ["ingestion-freshness"]
                    scope.set_context("ingestion", report)
                    sentry_sdk.capture_message("EDGAR ingestion requires attention", level="error")
                sentry_sdk.flush(timeout=5)
            raise CommandError("Ingestion freshness or coverage requires attention; see JSON report")
