"""Parse Form C primary_doc.xml.

Form C variants share the same edgarSubmission envelope as Form D but the
offeringData section is crowdfunding-specific."""

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
    if v in ("true", "yes", "1", "y"):
        return True
    if v in ("false", "no", "0", "n"):
        return False
    return None


def parse_form_c(xml_bytes: bytes, accession_number: str) -> ParsedCrowdfundingFiling:
    parser = etree.XMLParser(recover=True, huge_tree=False)
    root = etree.fromstring(xml_bytes, parser=parser)

    pf = ParsedCrowdfundingFiling(
        accession_number=accession_number,
        raw_xml=xml_bytes.decode("utf-8", errors="replace"),
    )

    header = root.find(".//headerData")
    offering = root.find(".//offeringData")

    if header is not None:
        sub_type = _text(header, ".//submissionType") or _text(header, "submissionType")
        if sub_type:
            pf.form_type = sub_type
            pf.is_amendment = "/A" in sub_type
        fd = _text(header, ".//filingDate") or _text(header, "filerInfo/filingDate")
        pf.filing_date = _parse_date(fd)

    # Issuer info — Form C nests it under offeringData/issuerInfo (vs Form D's primaryIssuer)
    issuer_el = root.find(".//issuerInfo") or (
        offering.find(".//issuerInfo") if offering is not None else None
    )
    if issuer_el is not None:
        pf.issuer.cik = _text(issuer_el, "cik").lstrip("0") or _text(issuer_el, "cik")
        pf.issuer.name = _text(issuer_el, "nameOfIssuer") or _text(issuer_el, "issuerName")
        pf.issuer.entity_type = _text(issuer_el, "legalStatusForm")
        pf.issuer.jurisdiction = (
            _text(issuer_el, "jurisdictionOrganization")
            or _text(issuer_el, "jurisdictionOfInc")
        )
        pf.issuer.year_of_incorporation = (
            _text(issuer_el, "dateIncorporation")[:4]
            or _text(issuer_el, "yearOfInc/value")
        )
        addr = issuer_el.find("issuerAddress") or issuer_el.find("issuerAddressInfo")
        if addr is not None:
            pf.issuer.street = _text(addr, "street1") or _text(addr, "addressLine1")
            pf.issuer.city = _text(addr, "city")
            pf.issuer.state = _text(addr, "stateOrCountry") or _text(addr, "state")
            pf.issuer.zip_code = _text(addr, "zipCode") or _text(addr, "postalCode")
        pf.issuer.phone = _text(issuer_el, "issuerPhoneNumber") or _text(issuer_el, "phone")

    # Intermediary
    intermediary = root.find(".//intermediaryInfo") or (
        offering.find(".//intermediaryInfo") if offering is not None else None
    )
    if intermediary is not None:
        pf.intermediary_name = _text(intermediary, "intermediaryName") or _text(intermediary, "name")
        pf.intermediary_cik = (
            _text(intermediary, "intermediaryCik").lstrip("0")
            or _text(intermediary, "cik").lstrip("0")
        )

    # Offering data
    if offering is not None:
        info = offering.find(".//offeringInfo") or offering
        pf.target_offering_amount = _int(info, ".//targetOfferingAmount") or _int(
            info, ".//offeringAmount"
        )
        pf.maximum_offering_amount = _int(info, ".//maximumOfferingAmount")
        pf.offering_deadline = _parse_date(_text(info, ".//deadlineDate") or _text(info, ".//offeringDeadline"))
        pf.security_type = _text(info, ".//securityOfferedType")[:128] or _text(info, ".//securityOffered")[:128]
        pf.price_per_security = _decimal(info, ".//pricePerSecurity")
        pf.oversubscription_accepted = _bool(info, ".//oversubscriptionAccepted")

        fc = offering.find(".//financialCondition") or offering
        pf.total_assets = _int(fc, ".//totalAssetMostRecentFiscalYear") or _int(fc, ".//totalAsset")
        pf.cash_equivalents = _int(fc, ".//cashAndCashEquiMostRecentFiscalYear") or _int(
            fc, ".//cashAndCashEquivalents"
        )
        pf.short_term_debt = _int(fc, ".//shortTermDebtMostRecentFiscalYear") or _int(
            fc, ".//shortTermDebt"
        )
        pf.long_term_debt = _int(fc, ".//longTermDebtMostRecentFiscalYear") or _int(
            fc, ".//longTermDebt"
        )
        pf.revenues = _int(fc, ".//revenueMostRecentFiscalYear") or _int(fc, ".//revenues")
        pf.cost_of_goods_sold = _int(fc, ".//costGoodsSoldMostRecentFiscalYear") or _int(
            fc, ".//costGoodsSold"
        )
        pf.taxes_paid = _int(fc, ".//taxesPaidMostRecentFiscalYear") or _int(fc, ".//taxesPaid")
        pf.net_income = _int(fc, ".//netIncomeMostRecentFiscalYear") or _int(fc, ".//netIncome")

    # Related persons (officers/directors/promoters) — Form C calls these signaturesInfo or similar
    for rp in root.findall(".//signatureInfo/signature") + root.findall(
        ".//signaturesInfo/signature"
    ) + root.findall(".//relatedPersonsList/relatedPersonInfo"):
        first = _text(rp, ".//firstName") or _text(rp, "firstName")
        last = _text(rp, ".//lastName") or _text(rp, "lastName")
        full = " ".join(p for p in (first, last) if p).strip() or _text(rp, ".//signatureName")
        if not full:
            continue
        title = _text(rp, ".//signatureTitle") or _text(rp, ".//title") or "Signatory"
        pf.related_persons.append(
            ParsedRelatedPerson(name=full, relationship=title, city="", state="")
        )

    return pf
