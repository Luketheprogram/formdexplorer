"""Pull Form ADV firm records into our local DB.

Modes:
  --crd <ID>          Fetch and upsert a single adviser by CRD (IAPD JSON; gated).
  --query <NAME>      Search IAPD by name (also gated; works only with browser-side auth).
  --from-form-d       Iterate Form D Pooled Investment Fund issuers and try to find advisers.
  --bulk-csv <PATH>   Stream-parse a Form ADV bulk CSV (SEC archive zip's primary
                      'IA_FIRM' or 'BASEA*' table) and upsert every row whose
                      latest filing date falls in the past --since-days window.
                      Pass either a local path or an http(s) URL.

The SEC publishes the bulk CSVs at:
  https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data
2025+ data is only on adviserinfo.sec.gov (no public bulk feed); the most
comprehensive bulk source is 'adv-filing-data-20111105-20241231-part1.zip' +
'-part2.zip', which together cover Nov 2011 through Dec 2024.
"""

import csv
import io
import time
import zipfile
from datetime import date, datetime, timedelta

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from advisers.iapd import fetch_detail, parse_firm, search
from advisers.models import Adviser
from filings.models import Issuer, normalize_issuer_name


# Common SEC ADV CSV column aliases. Header names vary across SEC publications;
# the parser scans for the first column whose lowercased name matches any alias.
COL_ALIASES = {
    "crd": ("organization crd#", "organization crd #", "organization_crd", "filing id", "1b1", "crd"),
    "sec_file": ("sec#", "sec #", "sec_number", "1d", "sec_file_number"),
    "name": ("primary business name", "primary_business_name", "1b", "1a", "firm name", "legal name", "name"),
    "street": ("main office street address 1", "main_office_address_1", "1f1", "address1"),
    "city": ("main office city", "main_office_city", "1f3", "city"),
    "state": ("main office state", "main_office_state", "1f4", "state"),
    "zip": ("main office postal code", "main_office_postal_code", "1f5", "zip", "postal_code"),
    "phone": ("main office telephone number", "main_office_phone", "1f7", "phone"),
    "website": ("website address", "website", "websiteaddress"),
    "raum": (
        "5f(2)(c) regulatory assets under management",
        "5f2c regulatory aum",
        "regulatory aum",
        "regulatory_aum",
        "raum",
        "totalrAum",
    ),
    "discretionary_aum": (
        "5f(2)(a) discretionary",
        "discretionary aum",
        "discretionary_aum",
    ),
    "employees": ("5a", "total_employees", "number of employees", "totalemployees"),
    "clients": ("5c1", "total_clients", "number of clients"),
    "filing_date": (
        "datesubmitted",
        "date submitted",
        "execution date",
        "filing date",
        "filingdate",
        "latest_adv_filing_date",
        "signdate",
    ),
    "registration_status": ("registrationstatus", "registration status", "status"),
}


def _resolve_columns(headers: list[str]) -> dict[str, int | None]:
    norm = [(h or "").strip().lower() for h in headers]
    out: dict[str, int | None] = {}
    for key, aliases in COL_ALIASES.items():
        idx = None
        for alias in aliases:
            if alias in norm:
                idx = norm.index(alias)
                break
        out[key] = idx
    return out


def _parse_int(val: str) -> int | None:
    if val is None:
        return None
    s = str(val).strip().replace(",", "").replace("$", "")
    if not s or s.lower() in ("na", "n/a", "none", "null"):
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _parse_date(val: str) -> date | None:
    if not val:
        return None
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d", "%d-%b-%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


class Command(BaseCommand):
    help = "Upsert Form ADV firms from SEC's IAPD JSON API."

    def add_arguments(self, parser):
        g = parser.add_mutually_exclusive_group(required=True)
        g.add_argument("--crd", type=str)
        g.add_argument("--query", type=str)
        g.add_argument("--from-form-d", action="store_true")
        g.add_argument("--bulk-csv", type=str,
                       help="Path or URL to a SEC Form ADV bulk CSV (or zip)")
        parser.add_argument("--csv-name", type=str, default="",
                            help="When the bulk source is a zip, the CSV filename inside it (else first .csv).")
        parser.add_argument("--since-days", type=int, default=730,
                            help="Skip rows whose latest filing date is older than this (default 2 years)")
        parser.add_argument("--limit", type=int, default=200,
                            help="Max issuers to scan in --from-form-d mode")
        parser.add_argument("--throttle-ms", type=int, default=200,
                            help="Sleep between IAPD requests")
        parser.add_argument("--max-rows", type=int, default=0,
                            help="Stop after N rows in bulk-csv mode (0 = no cap)")

    def handle(self, *args, **opts):
        throttle = opts["throttle_ms"] / 1000.0
        if opts.get("crd"):
            self._upsert_one(opts["crd"])
            return
        if opts.get("query"):
            self._search_and_upsert(opts["query"], throttle)
            return
        if opts.get("bulk_csv"):
            self._bulk_csv(
                opts["bulk_csv"],
                csv_name=opts.get("csv_name") or "",
                since_days=opts.get("since_days") or 730,
                max_rows=opts.get("max_rows") or 0,
            )
            return
        self._from_form_d(opts["limit"], throttle)

    def _bulk_csv(self, src: str, csv_name: str, since_days: int, max_rows: int):
        cutoff = date.today() - timedelta(days=since_days) if since_days > 0 else None

        if src.lower().startswith(("http://", "https://")):
            self.stdout.write(f"Downloading {src}")
            ua = getattr(settings, "EDGAR_USER_AGENT", "Form D Explorer luke@dawncrestconsulting.com")
            r = requests.get(src, headers={"User-Agent": ua}, timeout=300, stream=True)
            r.raise_for_status()
            blob = r.content
        else:
            with open(src, "rb") as fh:
                blob = fh.read()

        if src.lower().endswith(".zip") or blob[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                if not names:
                    raise CommandError("No .csv files inside the zip.")
                pick = csv_name if csv_name in names else names[0]
                self.stdout.write(f"Reading {pick} from zip ({len(names)} csv(s) inside)")
                with zf.open(pick) as fh:
                    text = fh.read().decode("utf-8-sig", errors="replace")
        else:
            text = blob.decode("utf-8-sig", errors="replace")

        reader = csv.reader(io.StringIO(text))
        try:
            headers = next(reader)
        except StopIteration:
            raise CommandError("Empty CSV.")
        cols = _resolve_columns(headers)
        missing = [k for k in ("crd", "name") if cols.get(k) is None]
        if missing:
            self.stdout.write(self.style.WARNING(
                f"Headers don't include {missing}. First few headers: {headers[:8]}"
            ))
            return

        stats = {"rows": 0, "upserted": 0, "skipped_old": 0, "skipped_no_crd": 0}
        latest_per_crd: dict[str, dict] = {}

        for row in reader:
            stats["rows"] += 1
            if max_rows and stats["rows"] > max_rows:
                break

            def cell(key: str) -> str:
                idx = cols.get(key)
                if idx is None or idx >= len(row):
                    return ""
                return (row[idx] or "").strip()

            crd = cell("crd")
            if not crd:
                stats["skipped_no_crd"] += 1
                continue
            name = cell("name")
            if not name:
                continue
            f_date = _parse_date(cell("filing_date"))
            if cutoff and f_date and f_date < cutoff:
                stats["skipped_old"] += 1
                continue
            existing = latest_per_crd.get(crd)
            if existing and existing["filing_date"] and f_date and f_date <= existing["filing_date"]:
                continue
            latest_per_crd[crd] = {
                "crd": crd,
                "sec_file_number": cell("sec_file"),
                "name": name,
                "street": cell("street"),
                "city": cell("city"),
                "state": cell("state")[:8],
                "zip_code": cell("zip")[:16],
                "phone": cell("phone")[:32],
                "website": cell("website") if cell("website").startswith("http") else "",
                "regulatory_aum": _parse_int(cell("raum")),
                "discretionary_aum": _parse_int(cell("discretionary_aum")),
                "num_employees": _parse_int(cell("employees")),
                "num_clients": _parse_int(cell("clients")),
                "registration_status": cell("registration_status"),
                "filing_date": f_date,
            }
            if stats["rows"] % 5000 == 0:
                self.stdout.write(f"  scanned {stats['rows']} rows, {len(latest_per_crd)} unique CRDs so far")

        self.stdout.write(f"Upserting {len(latest_per_crd)} advisers...")
        for n, payload in enumerate(latest_per_crd.values(), 1):
            payload.pop("filing_date", None)
            with transaction.atomic():
                Adviser.objects.update_or_create(
                    crd=payload.pop("crd"),
                    defaults=payload,
                )
            stats["upserted"] += 1
            if n % 1000 == 0:
                self.stdout.write(f"  {n}/{len(latest_per_crd)}")
        self.stdout.write(self.style.SUCCESS(f"Done: {stats}"))

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
