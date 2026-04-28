"""Pull Form ADV firm records from SEC's IAPD JSON endpoints into our local DB.

Three modes:
  --crd <ID>      Fetch and upsert a single adviser by CRD.
  --query <NAME>  Search IAPD by name and upsert each hit's full detail.
  --from-form-d   Iterate Form D issuers tagged 'Pooled Investment Fund' that
                  don't yet have a matching adviser, and try to find them.
"""

import time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from advisers.iapd import fetch_detail, parse_firm, search
from advisers.models import Adviser
from filings.models import Issuer, normalize_issuer_name


class Command(BaseCommand):
    help = "Upsert Form ADV firms from SEC's IAPD JSON API."

    def add_arguments(self, parser):
        g = parser.add_mutually_exclusive_group(required=True)
        g.add_argument("--crd", type=str)
        g.add_argument("--query", type=str)
        g.add_argument("--from-form-d", action="store_true")
        parser.add_argument("--limit", type=int, default=200,
                            help="Max issuers to scan in --from-form-d mode")
        parser.add_argument("--throttle-ms", type=int, default=200,
                            help="Sleep between IAPD requests")

    def handle(self, *args, **opts):
        throttle = opts["throttle_ms"] / 1000.0
        if opts.get("crd"):
            self._upsert_one(opts["crd"])
            return
        if opts.get("query"):
            self._search_and_upsert(opts["query"], throttle)
            return
        self._from_form_d(opts["limit"], throttle)

    def _upsert_one(self, crd: str) -> Adviser | None:
        payload = fetch_detail(crd)
        if not payload:
            self.stdout.write(self.style.WARNING(f"  no IAPD detail for CRD {crd}"))
            return None
        data = parse_firm(payload)
        if not data.get("crd") or not data.get("name"):
            self.stdout.write(self.style.WARNING(f"  could not parse CRD {crd}"))
            return None
        with transaction.atomic():
            adviser, created = Adviser.objects.update_or_create(
                crd=data["crd"], defaults={k: v for k, v in data.items() if k != "crd"}
            )
        self.stdout.write(f"  {'created' if created else 'updated'}: {adviser.name} (CRD {adviser.crd})")
        return adviser

    def _search_and_upsert(self, query: str, throttle: float):
        hits = search(query, limit=20)
        if not hits:
            raise CommandError(f"No IAPD results for query: {query}")
        for hit in hits:
            crd = (hit.get("firmId") or hit.get("crdNumber") or hit.get("firmCRD") or "")
            crd = str(crd).strip()
            if not crd:
                continue
            self._upsert_one(crd)
            time.sleep(throttle)

    def _from_form_d(self, limit: int, throttle: float):
        existing = set(Adviser.objects.values_list("normalized_name", flat=True))
        seen: set[str] = set()
        scanned = 0
        for issuer in (
            Issuer.objects.filter(filings__industry_group__iexact="Pooled Investment Fund")
            .order_by("-updated_at")
            .distinct()
            .iterator()
        ):
            if scanned >= limit:
                break
            norm = issuer.normalized_name or normalize_issuer_name(issuer.name)
            if not norm or norm in seen or norm in existing:
                continue
            seen.add(norm)
            scanned += 1
            self.stdout.write(f"[{scanned}/{limit}] searching IAPD for {issuer.name!r}")
            self._search_and_upsert_for_issuer(issuer.name, throttle)

    def _search_and_upsert_for_issuer(self, issuer_name: str, throttle: float):
        hits = search(issuer_name, limit=3)
        for hit in hits:
            crd = (hit.get("firmId") or hit.get("crdNumber") or hit.get("firmCRD") or "")
            crd = str(crd).strip()
            if not crd:
                continue
            self._upsert_one(crd)
            time.sleep(throttle)
