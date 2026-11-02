"""Reproducible query/latency checks on an isolated public-data restore."""

import json
import statistics
import time
from pathlib import Path

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext


class Command(BaseCommand):
    help = "Benchmark only an owned local PostgreSQL public-data rehearsal; never production."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)
        parser.add_argument("--repetitions", type=int, default=7)

    def handle(self, *args, **options):
        db = connection.settings_dict
        if (
            connection.vendor != "postgresql"
            or not str(db["HOST"]).startswith("/private/tmp/")
            or not db["NAME"].startswith("formd_public_quality_")
        ):
            raise CommandError(
                "This harness is restricted to the owned local public-data restore."
            )
        if not 3 <= options["repetitions"] <= 15:
            raise CommandError("Choose 3–15 repetitions.")
        from filings.models import Filing

        if Filing.objects.count() < 100000:
            raise CommandError(
                "At least 100,000 actual public filing records are required."
            )
        client = Client()
        paths = [
            "/search/",
            "/search/?q=0000000123",
            "/search/?state=CA&sort=largest",
            "/research/",
            "/research/filing-activity/",
            "/research/analysis/industry-mix/",
            "/research/analysis/offering-distribution/",
            "/research/compare/?kind=state&category=CA&category=NY&category=TX",
            "/research/coverage/",
        ]
        results = []
        for path in paths:
            cache.clear()
            times, queries = [], []
            for _ in range(options["repetitions"]):
                start = time.perf_counter()
                with CaptureQueriesContext(connection) as captured:
                    response = client.get(path)
                if response.status_code != 200:
                    raise CommandError(f"{path} returned {response.status_code}.")
                times.append(round((time.perf_counter() - start) * 1000, 2))
                queries.append(len(captured))
            results.append(
                {
                    "path": path,
                    "cold_ms": times[0],
                    "warm_median_ms": statistics.median(times[1:]),
                    "worst_ms": max(times),
                    "cold_queries": queries[0],
                    "warm_max_queries": max(queries[1:]),
                    "html_bytes": len(response.content),
                }
            )
        report = {
            "scope": "Local PostgreSQL with actual public SEC records; application/server timings, not production latency or mobile Core Web Vitals.",
            "filings": Filing.objects.count(),
            "postgres": connection.pg_version,
            "repetitions": options["repetitions"],
            "routes": results,
        }
        Path(options["output"]).write_text(json.dumps(report, indent=2) + "\n")
        self.stdout.write(
            f'Benchmarked {len(results)} routes with {report["filings"]} actual public filings.'
        )
