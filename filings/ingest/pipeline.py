import logging
from datetime import date, datetime

from django.db import OperationalError, connection, transaction
from django.utils.text import slugify

from ..models import Filing, Issuer, RelatedPerson
from .edgar_client import EdgarClient
from .index_parser import (
    IndexEntry,
    accession_from_filename,
    daily_index_paths,
    iter_business_days,
    parse_form_idx,
    primary_doc_url,
)
from .xml_parser import ParsedFiling, parse_primary_doc


def _parse_index_date(raw: str) -> date | None:
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None

log = logging.getLogger(__name__)


class IngestPipeline:
    def __init__(self, client: EdgarClient | None = None, store_raw_xml: bool = True):
        self.client = client or EdgarClient()
        self.store_raw_xml = store_raw_xml

    def run(self, start: date, end: date) -> dict:
        stats = {"days": 0, "entries": 0, "parsed": 0, "upserted": 0, "errors": 0}
        for day in iter_business_days(start, end):
            stats["days"] += 1
            entries = self._fetch_day_index(day)
            stats["entries"] += len(entries)
            for e in entries:
                try:
                    parsed = self._fetch_and_parse(e)
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
                    log.exception("Failed to ingest %s: %s", e.filename, exc)
        return stats

    def _fetch_day_index(self, day: date):
        for path in daily_index_paths(day):
            try:
                text = self.client.get_text(path)
            except Exception as exc:  # noqa: BLE001
                log.warning("No index at %s: %s", path, exc)
                continue
            return parse_form_idx(text)
        return []

    def _fetch_and_parse(self, entry: IndexEntry) -> ParsedFiling | None:
        url = primary_doc_url(entry.filename)
        accession = accession_from_filename(entry.filename)
        try:
            xml_bytes = self.client.get_bytes(url)
        except Exception as exc:  # noqa: BLE001
            log.warning("No primary_doc.xml for %s: %s", accession, exc)
            return None
        pf = parse_primary_doc(xml_bytes, accession)
        if pf.filing_date is None:
            pf.filing_date = _parse_index_date(entry.filing_date)
        if pf.form_type not in ("D", "D/A"):
            pf.form_type = entry.form_type
            pf.is_amendment = entry.form_type == "D/A"
        if not self.store_raw_xml:
            pf.raw_xml = ""
        return pf

    @transaction.atomic
    def _upsert(self, pf: ParsedFiling) -> Filing:
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
        filing, _ = Filing.objects.update_or_create(
            accession_number=pf.accession_number,
            defaults={
                "issuer": issuer,
                "filing_date": pf.filing_date,
                "form_type": pf.form_type,
                "is_amendment": pf.is_amendment,
                "offering_type": pf.offering_type,
                "total_offering_amount": pf.total_offering_amount,
                "total_amount_sold": pf.total_amount_sold,
                "minimum_investment": pf.minimum_investment,
                "num_investors": pf.num_investors,
                "sales_commission": pf.sales_commission,
                "finders_fees": pf.finders_fees,
                "industry_group": pf.industry_group,
                "banker_count": pf.banker_count,
                "banker_names": pf.banker_names,
                "raw_xml": pf.raw_xml,
            },
        )
        filing.related_persons.all().delete()
        for rp in pf.related_persons:
            if rp.name:
                RelatedPerson.objects.create(
                    filing=filing,
                    name=rp.name,
                    relationship=rp.relationship,
                    city=rp.city,
                    state=rp.state,
                )
        return filing
