import logging
from datetime import date, datetime, timedelta

from django.db import OperationalError, connection, transaction
from django.utils.text import slugify

from crowdfunding.ingest.xml_parser import parse_form_c
from crowdfunding.models import CrowdfundingFiling
from filings.ingest.edgar_client import EdgarClient
from filings.ingest.index_parser import (
    IndexEntry,
    accession_from_filename,
    daily_index_paths,
    iter_business_days,
    parse_form_idx,
    primary_doc_url,
)
from filings.models import Issuer, normalize_issuer_name

log = logging.getLogger(__name__)

FORM_C_TYPES = ("C", "C/A", "C-U", "C-AR", "C-AR/A", "C-TR", "C-W")


def _parse_index_date(raw: str) -> date | None:
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


class FormCPipeline:
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
                    try:
                        self._upsert(parsed)
                    except OperationalError as db_exc:
                        log.warning("DB connection dropped: %s; reconnecting", db_exc)
                        connection.close()
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
            return parse_form_idx(text, form_types=FORM_C_TYPES)
        return []

    def _fetch_and_parse(self, entry: IndexEntry):
        url = primary_doc_url(entry.filename)
        accession = accession_from_filename(entry.filename)
        try:
            xml_bytes = self.client.get_bytes(url)
        except Exception as exc:  # noqa: BLE001
            log.warning("No primary_doc.xml for %s: %s", accession, exc)
            return None
        pf = parse_form_c(xml_bytes, accession)
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
        CrowdfundingFiling.objects.update_or_create(
            accession_number=pf.accession_number,
            defaults={
                "issuer": issuer,
                "filing_date": pf.filing_date,
                "form_type": pf.form_type,
                "is_amendment": pf.is_amendment,
                "intermediary_name": pf.intermediary_name,
                "intermediary_cik": pf.intermediary_cik,
                "target_offering_amount": pf.target_offering_amount,
                "maximum_offering_amount": pf.maximum_offering_amount,
                "offering_deadline": pf.offering_deadline,
                "security_type": pf.security_type,
                "price_per_security": pf.price_per_security,
                "oversubscription_accepted": pf.oversubscription_accepted,
                "total_assets": pf.total_assets,
                "cash_equivalents": pf.cash_equivalents,
                "short_term_debt": pf.short_term_debt,
                "long_term_debt": pf.long_term_debt,
                "revenues": pf.revenues,
                "cost_of_goods_sold": pf.cost_of_goods_sold,
                "taxes_paid": pf.taxes_paid,
                "net_income": pf.net_income,
                "raw_xml": pf.raw_xml,
            },
        )
