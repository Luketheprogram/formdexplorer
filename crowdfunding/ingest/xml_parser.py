"""Parse Form C primary_doc.xml.

Form C XML uses namespaces (xmlns="http://www.sec.gov/edgar/formc" plus a
common namespace for address fields). lxml's .find() with bare tag names
doesn't match namespaced elements, so we strip namespace URIs from every
tag once at the top, then traverse with plain-name paths."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from lxml import etree

from filings.ingest.xml_parser import ParsedIssuer, ParsedRelatedPerson, _int, _parse_date, _text


@dataclass
class ParsedCrowdfundingFiling:
    accession_number: str = ""
    filing_date: date | None = None
    form_type: str = "C"
    is_amendment: bool = False
    intermediary_name: str = ""
    intermediary_cik: str = ""
    target_offering_amount: int | None = None
    maximum_offering_amount: int | None = None
    offering_deadline: date | None = None
    security_type: str = ""
    price_per_security: Decimal | None = None
    oversubscription_accepted: bool | None = None
    total_assets: int | None = None
    cash_equivalents: int | None = None
    short_term_debt: int | None = None
    long_term_debt: int | None = None
    revenues: int | None = None
    cost_of_goods_sold: int | None = None
    taxes_paid: int | None = None
    net_income: int | None = None
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


def _bool(el, path: str) -> bool | None:
    v = _text(el, path).strip().lower()
    if v in ("true", "yes", "y"):
        return True
    if v in ("false", "no", "n"):
        return False
    return None


def parse_form_c(xml_bytes: bytes, accession_number: str) -> ParsedCrowdfundingFiling:
    parser = etree.XMLParser(recover=True, huge_tree=False)
    root = etree.fromstring(xml_bytes, parser=parser)
    _strip_ns(root)

    pf = ParsedCrowdfundingFiling(
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
        # Issuer CIK lives in filerCredentials, possibly under <filer> or directly
        for path in (
            ".//filerCredentials/filerCik",
            ".//filerCredentials/cik",
            ".//issuerCredentials/cik",
            ".//filer/filerCredentials/filerCik",
        ):
            cik = _text(header, path)
            if cik:
                pf.issuer.cik = cik.lstrip("0") or cik
                break

    if form_data is None:
        return pf

    issuer_info = form_data.find(".//issuerInfo")
    if issuer_info is None:
        issuer_info = form_data.find(".//issuerInformation/issuerInfo")
    if issuer_info is None:
        issuer_info = form_data.find(".//issuerInformation")
    if issuer_info is not None:
        pf.issuer.name = (
            _text(issuer_info, "nameOfIssuer")
            or _text(issuer_info, ".//nameOfIssuer")
            or _text(issuer_info, "issuerName")
        )
        pf.issuer.entity_type = (
            _text(issuer_info, ".//legalStatusForm")
            or _text(issuer_info, "legalStatus/legalStatusForm")
        )
        pf.issuer.jurisdiction = (
            _text(issuer_info, ".//jurisdictionOrganization")
            or _text(issuer_info, "legalStatus/jurisdictionOrganization")
        )
        di = _text(issuer_info, ".//dateIncorporation")
        if di:
            # Could be MM-DD-YYYY or YYYY-MM-DD
            for token in (di[-4:], di[:4]):
                if token.isdigit():
                    pf.issuer.year_of_incorporation = token
                    break
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
                _text(addr, "zipCode") or _text(addr, ".//zipCode") or _text(addr, ".//postalCode")
            )[:16]
        pf.issuer.phone = _text(issuer_info, ".//issuerPhoneNumber")[:32]

    # Intermediary (funding portal): companyName + commissionCik live alongside issuerInfo
    inter = form_data.find(".//issuerInformation")
    if inter is None:
        inter = form_data
    if inter is not None:
        pf.intermediary_name = _text(inter, "companyName") or _text(inter, ".//companyName")
        pf.intermediary_cik = (_text(inter, "commissionCik") or _text(inter, ".//commissionCik")).lstrip("0")

    # Offering info
    off = form_data.find(".//offeringInformation")
    if off is None:
        off = form_data
    if off is not None:
        pf.target_offering_amount = (
            _int(off, ".//targetOfferingAmount") or _int(off, ".//offeringAmount")
        )
        pf.maximum_offering_amount = _int(off, ".//maximumOfferingAmount")
        pf.offering_deadline = _parse_date(_text(off, ".//deadlineDate"))
        pf.security_type = (_text(off, ".//securityOfferedType") or _text(off, ".//securityOffered"))[:128]
        pf.price_per_security = _decimal(off, ".//price") or _decimal(off, ".//pricePerSecurity")
        pf.oversubscription_accepted = (
            _bool(off, ".//overSubscriptionAccepted") or _bool(off, ".//oversubscriptionAccepted")
        )

    # Financials live under various paths depending on form variant
    fc = form_data.find(".//annualReportDisclosureRequirements")
    if fc is None:
        fc = form_data.find(".//financialCondition")
    if fc is None:
        fc = form_data
    if fc is not None:
        pf.total_assets = (
            _int(fc, ".//totalAssetMostRecentFiscalYear")
            or _int(fc, ".//totalAsset")
            or _int(fc, ".//totalAssets")
        )
        pf.cash_equivalents = (
            _int(fc, ".//cashAndCashEquiMostRecentFiscalYear")
            or _int(fc, ".//cashAndCashEquivalents")
            or _int(fc, ".//cash")
        )
        pf.short_term_debt = (
            _int(fc, ".//shortTermDebtMostRecentFiscalYear") or _int(fc, ".//shortTermDebt")
        )
        pf.long_term_debt = (
            _int(fc, ".//longTermDebtMostRecentFiscalYear") or _int(fc, ".//longTermDebt")
        )
        pf.revenues = (
            _int(fc, ".//revenueMostRecentFiscalYear")
            or _int(fc, ".//revenues")
            or _int(fc, ".//revenue")
        )
        pf.cost_of_goods_sold = (
            _int(fc, ".//costGoodsSoldMostRecentFiscalYear") or _int(fc, ".//costGoodsSold")
        )
        pf.taxes_paid = (
            _int(fc, ".//taxesPaidMostRecentFiscalYear") or _int(fc, ".//taxesPaid")
        )
        pf.net_income = (
            _int(fc, ".//netIncomeMostRecentFiscalYear")
            or _int(fc, ".//netIncome")
        )

    # Signatories / officers
    for rp in root.findall(".//signatureInfo/signature") + root.findall(".//signaturesInfo/signature"):
        first = _text(rp, ".//firstName")
        last = _text(rp, ".//lastName")
        full = " ".join(p for p in (first, last) if p).strip() or _text(rp, ".//signatureName")
        if not full:
            continue
        title = _text(rp, ".//signatureTitle") or _text(rp, ".//title") or "Signatory"
        pf.related_persons.append(
            ParsedRelatedPerson(name=full, relationship=title, city="", state="")
        )

    return pf
