import logging
from datetime import date, datetime, timedelta

from django.db import transaction
from django.utils.text import slugify

from filings.ingest.edgar_client import EdgarClient
from filings.ingest.index_parser import (
    IndexEntry,
    accession_from_filename,
    daily_index_paths,
    iter_business_days,
    parse_form_idx,
    primary_doc_url,
)
from filings.models import Issuer
from rega.ingest.xml_parser import parse_form_1a
from rega.models import Form1AFiling

log = logging.getLogger(__name__)

FORM_1A_TYPES = ("1-A", "1-A/A", "1-A POS", "1-K", "1-K/A", "1-U", "1-U/A", "1-Z", "1-Z/A")


def _parse_index_date(raw: str) -> date | None:
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


class Form1APipeline:
    def __init__(self, client: EdgarClient | None = None, store_raw_xml: bool = True):
        self.client = client or EdgarClient()
        self.store_raw_xml = store_raw_xml

    def run(self, start: date, end: date) -> dict:
        stats = {"days": 0, "entries": 0, "parsed": 0, "upserted": 0, "errors": 0}
        for day in iter_business_days(start, end):
            stats["days"] += 1
            for entry in self._fetch_day_index(day):
                stats["entries"] += 1
                try:
                    parsed = self._fetch_and_parse(entry)
                    if parsed is None:
                        continue
                    stats["parsed"] += 1
                    self._upsert(parsed)
                    stats["upserted"] += 1
                except Exception as exc:  # noqa: BLE001
                    stats["errors"] += 1
                    log.exception("Failed to ingest %s: %s", entry.filename, exc)
        return stats

    def _fetch_day_index(self, day: date):
        for path in daily_index_paths(day):
            try:
                text = self.client.get_text(path)
            except Exception as exc:  # noqa: BLE001
                log.warning("No index at %s: %s", path, exc)
                continue
            return parse_form_idx(text, form_types=FORM_1A_TYPES)
        return []

    def _fetch_and_parse(self, entry: IndexEntry):
        url = primary_doc_url(entry.filename)
        accession = accession_from_filename(entry.filename)
        try:
            xml_bytes = self.client.get_bytes(url)
        except Exception as exc:  # noqa: BLE001
            log.warning("No primary_doc.xml for %s: %s", accession, exc)
            return None
        pf = parse_form_1a(xml_bytes, accession)
        if pf.filing_date is None:
            pf.filing_date = _parse_index_date(entry.filing_date)
        if not pf.form_type:
            pf.form_type = entry.form_type
        pf.is_amendment = "/A" in pf.form_type
        if not self.store_raw_xml:
            pf.raw_xml = ""
        return pf

    @transaction.atomic
    def _upsert(self, pf):
        cik = pf.issuer.cik.strip()
        if not cik:
            raise ValueError(f"Missing CIK for {pf.accession_number}")
        issuer, _ = Issuer.objects.update_or_create(
            cik=cik,
            defaults={
                "name": pf.issuer.name or f"CIK {cik}",
                "name_slug": slugify(pf.issuer.name or f"cik-{cik}")[:250] or f"cik-{cik}",
                "entity_type": pf.issuer.entity_type,
                "jurisdiction": pf.issuer.jurisdiction,
                "year_of_incorporation": pf.issuer.year_of_incorporation,
                "street": pf.issuer.street,
                "city": pf.issuer.city,
                "state": pf.issuer.state,
                "zip_code": pf.issuer.zip_code,
                "phone": pf.issuer.phone,
            },
        )
        Form1AFiling.objects.update_or_create(
            accession_number=pf.accession_number,
            defaults={
                "issuer": issuer,
                "filing_date": pf.filing_date,
                "form_type": pf.form_type,
                "is_amendment": pf.is_amendment,
                "tier": pf.tier,
                "total_offering_amount": pf.total_offering_amount,
                "total_amount_sold": pf.total_amount_sold,
                "price_per_security": pf.price_per_security,
                "security_type": pf.security_type,
                "over_allotment": pf.over_allotment,
                "jurisdictions": pf.jurisdictions,
                "total_assets": pf.total_assets,
                "total_liabilities": pf.total_liabilities,
                "total_revenues": pf.total_revenues,
                "net_income": pf.net_income,
                "cash_equivalents": pf.cash_equivalents,
                "raw_xml": pf.raw_xml,
            },
        )
