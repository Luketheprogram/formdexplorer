from rega.ingest.documents import validate_xml
from datetime import date, datetime

from django.db import transaction
from filings.ingest.issuers import upsert_issuer

from crowdfunding.ingest.xml_parser import parse_form_c
from rega.ingest.documents import primary_xml
from crowdfunding.models import CrowdfundingFiling
from filings.ingest.edgar_client import EdgarClient
from filings.ingest.index_parser import (
    IndexEntry, SourceCIKMismatch,
    accession_from_filename,
    daily_index_paths,
    parse_form_idx,
)

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

    dataset = "c"
    filing_model = CrowdfundingFiling

    def run(self, start: date, end: date, **kwargs) -> dict:
        from filings.ingest.reliability import run_pipeline
        return run_pipeline(self, start, end, **kwargs)

    def _fetch_day_index(self, day: date):
        # A missing or malformed index is durable failed work, never an empty day.
        text = self.client.get_text(daily_index_paths(day)[0])
        return parse_form_idx(text, form_types=FORM_C_TYPES, strict=True)

    def _fetch_and_parse(self, entry: IndexEntry):
        accession = accession_from_filename(entry.filename)
        xml_bytes = primary_xml(self.client, entry)
        pf = parse_form_c(validate_xml(xml_bytes, required_tag="formData", expected_form=entry.form_type), accession)
        index_cik = entry.cik.lstrip("0")
        if pf.issuer.cik and pf.issuer.cik.lstrip("0") != index_cik:
            raise SourceCIKMismatch(accession, pf.issuer.cik)
        pf.issuer.cik = index_cik
        if not pf.issuer.name:
            pf.issuer.name = entry.company.strip()
        if pf.filing_date is None:
            pf.filing_date = _parse_index_date(entry.filing_date)
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
        issuer = upsert_issuer(pf.issuer, pf.filing_date, pf.accession_number)
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
                **({"raw_xml": pf.raw_xml} if pf.raw_xml else {}),
            },
        )
