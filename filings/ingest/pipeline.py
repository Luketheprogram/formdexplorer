from rega.ingest.documents import validate_xml
from datetime import date, datetime

from django.db import transaction
from filings.ingest.issuers import upsert_issuer

from ..models import Filing, RelatedPerson
from .edgar_client import EdgarClient
from .index_parser import (
    IndexEntry, SourceCIKMismatch,
    accession_from_filename,
    daily_index_paths,
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


class IngestPipeline:
    def __init__(self, client: EdgarClient | None = None, store_raw_xml: bool = True):
        self.client = client or EdgarClient()
        self.store_raw_xml = store_raw_xml

    dataset = "d"
    filing_model = Filing

    def run(self, start: date, end: date, **kwargs) -> dict:
        from filings.ingest.reliability import run_pipeline
        return run_pipeline(self, start, end, **kwargs)

    def _fetch_day_index(self, day: date):
        # A missing or malformed index is durable failed work, never an empty day.
        text = self.client.get_text(daily_index_paths(day)[0])
        return parse_form_idx(text, form_types=("D", "D/A"), strict=True)

    def _fetch_and_parse(self, entry: IndexEntry) -> ParsedFiling | None:
        url = primary_doc_url(entry.filename)
        accession = accession_from_filename(entry.filename)
        xml_bytes = self.client.get_bytes(url)
        pf = parse_primary_doc(validate_xml(xml_bytes, required_tag="primaryIssuer", expected_form=entry.form_type), accession)
        index_cik = entry.cik.lstrip("0")
        if pf.issuer.cik and pf.issuer.cik.lstrip("0") != index_cik:
            raise SourceCIKMismatch(accession, pf.issuer.cik)
        pf.issuer.cik = index_cik
        if not pf.issuer.name:
            pf.issuer.name = entry.company.strip()
        if pf.filing_date is None:
            pf.filing_date = _parse_index_date(entry.filing_date)
        # The SEC index supplies the submission type even when XML omits it.
        # ParsedFiling defaults to D, so testing that default used to silently
        # discard D/A from the index. Prefer this authoritative entry for both.
        if entry.form_type in ("D", "D/A"):
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
        issuer = upsert_issuer(pf.issuer, pf.filing_date, pf.accession_number)
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
                **({"raw_xml": pf.raw_xml} if pf.raw_xml else {}),
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
