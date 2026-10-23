from datetime import date, datetime

from django.db import transaction
from filings.ingest.issuers import upsert_issuer

from filings.ingest.edgar_client import EdgarClient
from filings.ingest.index_parser import (
    IndexEntry, SourceCIKMismatch,
    accession_from_filename,
    daily_index_paths,
    parse_form_idx,
)
from rega.ingest.xml_parser import parse_form_1a, ParsedRegAFiling
from rega.ingest.documents import primary_document, validate_xml
from rega.models import Form1AFiling

FORM_1A_TYPES = ("1-A", "1-A/A", "1-A POS", "1-K", "1-K/A", "1-U", "1-U/A", "1-Z", "1-Z/A", "1-SA", "1-SA/A", "1-A-W", "1-Z-W", "1-A-W/A", "1-Z-W/A")


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

    dataset = "a"
    filing_model = Form1AFiling

    def run(self, start: date, end: date, **kwargs) -> dict:
        from filings.ingest.reliability import run_pipeline
        return run_pipeline(self, start, end, **kwargs)

    def _fetch_day_index(self, day: date):
        # A missing or malformed index is durable failed work, never an empty day.
        text = self.client.get_text(daily_index_paths(day)[0])
        return parse_form_idx(text, form_types=FORM_1A_TYPES, strict=True)

    def _fetch_and_parse(self, entry: IndexEntry):
        accession = accession_from_filename(entry.filename)
        document = primary_document(self.client, entry)
        if document.structured:
            pf = parse_form_1a(validate_xml(document.content, required_tag="formData", expected_form=entry.form_type), accession)
        else:
            pf = ParsedRegAFiling(accession_number=accession, metadata_only=True)
        index_cik = entry.cik.lstrip("0")
        if pf.issuer.cik and pf.issuer.cik.lstrip("0") != index_cik:
            raise SourceCIKMismatch(accession, pf.issuer.cik)
        pf.issuer.cik = index_cik
        if not pf.issuer.name:
            pf.issuer.name = entry.company.strip()
        if pf.filing_date is None:
            pf.filing_date = _parse_index_date(entry.filing_date)
        pf.form_type = entry.form_type
        pf.is_amendment = "/A" in pf.form_type or pf.form_type == "1-A POS"
        if not self.store_raw_xml:
            pf.raw_xml = ""
        return pf

    @transaction.atomic
    def _upsert(self, pf):
        cik = pf.issuer.cik.strip()
        if not cik:
            raise ValueError(f"Missing CIK for {pf.accession_number}")
        if pf.metadata_only:
            from filings.models import Issuer
            # A validated HTML filing can add coverage without changing any known
            # issuer values or the freshness baseline for its structured identity.
            issuer, _ = Issuer.objects.select_for_update().get_or_create(
                cik=cik, defaults={"name": pf.issuer.name[:255] or f"CIK {cik}"})
            Form1AFiling.objects.get_or_create(
                accession_number=pf.accession_number,
                defaults={"issuer": issuer, "filing_date": pf.filing_date,
                          "form_type": pf.form_type, "is_amendment": pf.is_amendment})
            return
        issuer = upsert_issuer(pf.issuer, pf.filing_date, pf.accession_number)
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
                **({"raw_xml": pf.raw_xml} if pf.raw_xml else {}),
            },
        )
