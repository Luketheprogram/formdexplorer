"""Parse Form 1-A primary_doc.xml.

Reg A+ XMLs use namespaces (xmlns='http://www.sec.gov/edgar/rega/...' plus
the common namespace for address fields). We strip namespaces once at the
top, then walk with plain-tag paths."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from lxml import etree

from filings.ingest.xml_parser import ParsedIssuer, ParsedRelatedPerson, _int, _parse_date, _text


@dataclass
class ParsedRegAFiling:
    accession_number: str = ""
    filing_date: date | None = None
    form_type: str = "1-A"
    is_amendment: bool = False
    tier: str = ""
    total_offering_amount: int | None = None
    total_amount_sold: int | None = None
    price_per_security: Decimal | None = None
    security_type: str = ""
    over_allotment: int | None = None
    jurisdictions: str = ""
    total_assets: int | None = None
    total_liabilities: int | None = None
    total_revenues: int | None = None
    net_income: int | None = None
    cash_equivalents: int | None = None
    issuer: ParsedIssuer = field(default_factory=ParsedIssuer)
    related_persons: list[ParsedRelatedPerson] = field(default_factory=list)
    raw_xml: str = ""


def _strip_ns(root):
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    etree.cleanup_namespaces(root)


def _decimal(el, path: str) -> Decimal | None:
    v = _text(el, path)
    if not v:
        return None
    try:
        return Decimal(v)
    except (InvalidOperation, TypeError, ValueError):
        return None


def parse_form_1a(xml_bytes: bytes, accession_number: str) -> ParsedRegAFiling:
    parser = etree.XMLParser(recover=True, huge_tree=False)
    root = etree.fromstring(xml_bytes, parser=parser)
    _strip_ns(root)

    pf = ParsedRegAFiling(
        accession_number=accession_number,
        raw_xml=xml_bytes.decode("utf-8", errors="replace"),
    )

    header = root.find(".//headerData")
    form_data = root.find(".//formData")

    if header is not None:
        sub_type = _text(header, ".//submissionType") or _text(header, "submissionType")
        if sub_type:
            pf.form_type = sub_type.strip()
            pf.is_amendment = "/A" in pf.form_type
        fd = _text(header, ".//filingDate")
        pf.filing_date = _parse_date(fd) if fd else None
        for path in (
            ".//issuerCredentials/cik",
            ".//filerCredentials/filerCik",
            ".//filerCredentials/cik",
            ".//filer/issuerCredentials/cik",
        ):
            cik = _text(header, path)
            if cik:
                pf.issuer.cik = cik.lstrip("0") or cik
                break

    if form_data is None:
        return pf

    issuer_info = form_data.find(".//issuerInfo")
    if issuer_info is None:
        issuer_info = form_data.find(".//primaryIssuer")
    if issuer_info is not None:
        if not pf.issuer.cik:
            pf.issuer.cik = (
                _text(issuer_info, "cik").lstrip("0") or _text(issuer_info, "cik")
            )
        pf.issuer.name = (
            _text(issuer_info, "entityName")
            or _text(issuer_info, "issuerName")
            or _text(issuer_info, ".//entityName")
        )
        pf.issuer.entity_type = _text(issuer_info, ".//entityType") or _text(
            issuer_info, ".//jurisdictionOrganizationType"
        )
        pf.issuer.jurisdiction = (
            _text(issuer_info, ".//jurisdictionOfInc")
            or _text(issuer_info, ".//jurisdictionOfOrganization")
        )
        yr = _text(issuer_info, ".//yearOfInc/value") or _text(
            issuer_info, ".//yearOfInc"
        )
        if yr:
            pf.issuer.year_of_incorporation = yr[:4]
        addr = issuer_info.find("issuerAddress")
        if addr is None:
            addr = issuer_info.find(".//issuerAddress")
        if addr is not None:
            pf.issuer.street = _text(addr, "street1") or _text(addr, ".//street1")
            pf.issuer.city = _text(addr, "city") or _text(addr, ".//city")
            pf.issuer.state = (
                _text(addr, "stateOrCountry") or _text(addr, ".//stateOrCountry")
            )[:8]
            pf.issuer.zip_code = (
                _text(addr, "zipCode") or _text(addr, ".//zipCode")
            )[:16]
        pf.issuer.phone = _text(issuer_info, ".//issuerPhoneNumber")[:32]

    # Tier — look for "tier1" / "tier2" boolean or text
    tier_text = _text(form_data, ".//regulationAItem") or _text(form_data, ".//tier")
    if tier_text:
        t = tier_text.strip().lower()
        if "tier 2" in t or t == "2":
            pf.tier = "Tier 2"
        elif "tier 1" in t or t == "1":
            pf.tier = "Tier 1"
        else:
            pf.tier = tier_text[:8]

    # Offering info
    pf.total_offering_amount = (
        _int(form_data, ".//offeringSalesAmounts/totalOfferingAmount")
        or _int(form_data, ".//totalOfferingAmount")
    )
    pf.total_amount_sold = (
        _int(form_data, ".//offeringSalesAmounts/totalAmountSold")
        or _int(form_data, ".//totalAmountSold")
    )
    pf.price_per_security = (
        _decimal(form_data, ".//pricePerSecurity")
        or _decimal(form_data, ".//offeringPrice")
    )
    pf.security_type = (_text(form_data, ".//securityOfferedType") or _text(form_data, ".//typeOfSecurity"))[:128]
    pf.over_allotment = _int(form_data, ".//overallotmentAmount") or _int(
        form_data, ".//overAllotmentAmount"
    )
    juris = form_data.findall(".//jurisdictionOfSecOffer/item") or form_data.findall(
        ".//jurisdictionsOfSecOffer/item"
    )
    if juris:
        pf.jurisdictions = ",".join((j.text or "").strip() for j in juris if j.text)[:255]

    # 1-K financials
    fc = form_data.find(".//annualReportFinancialStatements") or form_data
    pf.total_assets = _int(fc, ".//totalAssetsMostRecentFiscalYear") or _int(
        fc, ".//totalAssets"
    )
    pf.total_liabilities = _int(fc, ".//totalLiabilitiesMostRecentFiscalYear") or _int(
        fc, ".//totalLiabilities"
    )
    pf.total_revenues = _int(fc, ".//totalRevenuesMostRecentFiscalYear") or _int(
        fc, ".//totalRevenues"
    )
    pf.net_income = _int(fc, ".//netIncomeMostRecentFiscalYear") or _int(
        fc, ".//netIncome"
    )
    pf.cash_equivalents = _int(fc, ".//cashAndCashEquivalentsMostRecentFiscalYear") or _int(
        fc, ".//cashAndCashEquivalents"
    )

    # Signatories
    for rp in root.findall(".//signatureBlock") + root.findall(".//signature"):
        first = _text(rp, ".//firstName")
        last = _text(rp, ".//lastName")
        full = " ".join(p for p in (first, last) if p).strip() or _text(rp, ".//signatureName")
        if not full:
            continue
        title = _text(rp, ".//title") or _text(rp, ".//signatureTitle") or "Signatory"
        pf.related_persons.append(
            ParsedRelatedPerson(name=full, relationship=title, city="", state="")
        )

    return pf
