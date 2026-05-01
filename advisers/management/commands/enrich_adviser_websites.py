"""Loop through advisers without a website and try to find one via Clearbit.

Iterates by pre-materialized PK list rather than a server-side cursor so
a dropped connection doesn't kill the run mid-iteration."""

import time

from django.core.management.base import BaseCommand
from django.db import OperationalError, connection

from advisers.enrich import enrich_adviser
from advisers.models import Adviser


class Command(BaseCommand):
    help = "Enrich Adviser.website by Clearbit name → domain lookup."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Stop after N rows (0 = no cap)")
        parser.add_argument("--min-similarity", type=float, default=0.5)
        parser.add_argument("--throttle-ms", type=int, default=600)
        parser.add_argument("--force", action="store_true",
                            help="Re-lookup advisers that already have a website")

    def handle(self, *args, **opts):
        qs = Adviser.objects.all() if opts.get("force") else Adviser.objects.filter(website="")
        qs = qs.order_by("-regulatory_aum", "name")
        if opts.get("limit"):
            qs = qs[: opts["limit"]]

        # Materialize PKs once; small memory cost, survives connection drops.
        pks = list(qs.values_list("pk", flat=True))
        total = len(pks)
        self.stdout.write(f"Looking up websites for {total} advisers")
        throttle = opts["throttle_ms"] / 1000.0
        found = skipped = errors = 0

        for n, pk in enumerate(pks, 1):
            try:
                adviser = Adviser.objects.get(pk=pk)
            except OperationalError:
                connection.close()
                try:
                    adviser = Adviser.objects.get(pk=pk)
                except Exception as exc:  # noqa: BLE001
                    errors += 1
                    self.stdout.write(self.style.WARNING(f"fetch failed pk={pk}: {exc}"))
                    continue
            except Adviser.DoesNotExist:
                continue

            try:
                if enrich_adviser(adviser, min_similarity=opts["min_similarity"], force=opts.get("force", False)):
                    found += 1
                else:
                    skipped += 1
            except OperationalError as exc:
                connection.close()
                errors += 1
                self.stdout.write(self.style.WARNING(f"DB drop, will reconnect: {exc}"))
            except Exception as exc:  # noqa: BLE001
                errors += 1
                self.stdout.write(self.style.WARNING(f"err on {adviser.crd}: {exc}"))

            if n % 200 == 0:
                self.stdout.write(f"  {n}/{total}  found={found} skipped={skipped} errors={errors}")
            time.sleep(throttle)

        self.stdout.write(self.style.SUCCESS(
            f"Done: {found} websites set, {skipped} no match, {errors} errors"
        ))
