"""Parse Form D primary_doc.xml."""

from dataclasses import dataclass, field
from datetime import date, datetime

from lxml import etree


@dataclass
class ParsedIssuer:
    cik: str = ""
    name: str = ""
    entity_type: str = ""
    jurisdiction: str = ""
    year_of_incorporation: str = ""
    street: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    phone: str = ""


@dataclass
class ParsedRelatedPerson:
    name: str = ""
    relationship: str = ""
    city: str = ""
    state: str = ""


@dataclass
class ParsedFiling:
    accession_number: str = ""
    filing_date: date | None = None
    form_type: str = "D"
    is_amendment: bool = False
    offering_type: str = ""
    total_offering_amount: int | None = None
    total_amount_sold: int | None = None
    minimum_investment: int | None = None
    num_investors: int | None = None
    sales_commission: int | None = None
    finders_fees: int | None = None
    industry_group: str = ""
    issuer: ParsedIssuer = field(default_factory=ParsedIssuer)
    related_persons: list[ParsedRelatedPerson] = field(default_factory=list)
    raw_xml: str = ""


def _text(el, path: str) -> str:
    found = el.find(path)
    if found is None or found.text is None:
        return ""
    return found.text.strip()


def _int(el, path: str) -> int | None:
    v = _text(el, path)
    if not v:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _parse_date(v: str) -> date | None:
    if not v:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def parse_primary_doc(xml_bytes: bytes, accession_number: str) -> ParsedFiling:
    """Parse a Form D primary_doc.xml into a ParsedFiling dataclass."""
    parser = etree.XMLParser(recover=True, huge_tree=False)
    root = etree.fromstring(xml_bytes, parser=parser)

    header = root.find(".//headerData")
    offering = root.find(".//offeringData")
    pf = ParsedFiling(accession_number=accession_number, raw_xml=xml_bytes.decode("utf-8", errors="replace"))

    if header is not None:
        sub_type = _text(header, "submissionType") or _text(header, ".//submissionType")
        if sub_type:
            pf.form_type = "D/A" if sub_type.upper() == "D/A" else "D"
            pf.is_amendment = pf.form_type == "D/A"
        fd = _text(header, ".//filingDate") or _text(header, "filerInfo/filingDate")
        pf.filing_date = _parse_date(fd)

    # Issuer
    issuer_el = root.find(".//primaryIssuer")
    if issuer_el is None and offering is not None:
        issuer_el = offering.find(".//primaryIssuer")
    if issuer_el is not None:
        pf.issuer.cik = _text(issuer_el, "cik").lstrip("0") or _text(issuer_el, "cik")
        pf.issuer.name = _text(issuer_el, "entityName")
        pf.issuer.entity_type = _text(issuer_el, "entityType")
        pf.issuer.jurisdiction = _text(issuer_el, "jurisdictionOfInc")
        pf.issuer.year_of_incorporation = _text(issuer_el, "yearOfInc/value") or _text(
            issuer_el, ".//yearOfInc/value"
        )
        addr = issuer_el.find("issuerAddress")
        if addr is not None:
            pf.issuer.street = _text(addr, "street1")
            pf.issuer.city = _text(addr, "city")
            pf.issuer.state = _text(addr, "stateOrCountry")
            pf.issuer.zip_code = _text(addr, "zipCode")
        pf.issuer.phone = _text(issuer_el, "issuerPhoneNumber")

    # Offering details
    if offering is not None:
        industry = _text(offering, ".//industryGroup/industryGroupType") or _text(
            offering, ".//industryGroupType"
        )
        pf.industry_group = industry
        exemptions = [
            e.text.strip()
            for e in offering.findall(".//federalExemptionsExclusions/item")
            if e.text
        ]
        pf.offering_type = ", ".join(exemptions)[:128]
        pf.total_offering_amount = _int(offering, ".//offeringSalesAmounts/totalOfferingAmount")
        pf.total_amount_sold = _int(offering, ".//offeringSalesAmounts/totalAmountSold")
        pf.minimum_investment = _int(offering, ".//minimumInvestmentAccepted")
        pf.num_investors = _int(offering, ".//numberAlreadyInvested")
        pf.sales_commission = _int(offering, ".//salesCommissionsAmount")
        pf.finders_fees = _int(offering, ".//findersFeesAmount")

    # Related persons
    rp_list = root.findall(".//relatedPersonsList/relatedPersonInfo")
    for rp in rp_list:
        first = _text(rp, "relatedPersonName/firstName")
        middle = _text(rp, "relatedPersonName/middleName")
        last = _text(rp, "relatedPersonName/lastName")
        full = " ".join(p for p in (first, middle, last) if p).strip()
        rels = rp.findall(".//relationship")
        rel_val = rels[0].text.strip() if rels and rels[0].text else ""
        addr = rp.find("relatedPersonAddress")
        city = _text(addr, "city") if addr is not None else ""
        state = _text(addr, "stateOrCountry") if addr is not None else ""
        pf.related_persons.append(
            ParsedRelatedPerson(name=full, relationship=rel_val, city=city, state=state)
        )

    return pf
