"""Extract reproducible facts from stored documents; no network or source rewrites."""

import hashlib
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from lxml import etree
from django.utils import timezone
from filings.models import Filing
from crowdfunding.models import CrowdfundingFiling
from rega.models import Form1AFiling
from .models import DisclosureEvidence

EXTRACTION_VERSION = 2

MODELS = {"d": Filing, "c": CrowdfundingFiling, "a": Form1AFiling}
FIELDS = {
    "totalOfferingAmount": "Reported offering amount",
    "totalAmountSold": "Reported amount sold",
    "minimumInvestmentAccepted": "Reported minimum investment",
    "minimumInvestment": "Reported minimum investment",
    "totalNumberAlreadyInvested": "Reported investor count",
    "salesCommissions": "Reported sales commissions",
    "findersFees": "Reported finders fees",
    "maximumOfferingAmount": "Reported maximum offering",
    "targetOfferingAmount": "Reported target offering",
}


def record(dataset, accession):
    return (
        MODELS[dataset].objects.select_related("issuer").get(accession_number=accession)
    )


def numeric_state(raw):
    stripped = raw.strip()
    if not stripped:
        return {"state": "not_provided", "value": None, "raw": raw}
    if stripped.casefold() in {"indefinite", "unlimited"}:
        return {"state": "indefinite", "value": None, "raw": raw}
    if re.fullmatch(
        r"[0-9]+(?:\.[0-9]+)?|[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?", stripped
    ):
        from decimal import Decimal, InvalidOperation

        try:
            number = Decimal(stripped.replace(",", ""))
            if number <= 9223372036854775807:
                return {"state": "number", "value": str(number), "raw": raw}
        except InvalidOperation:
            pass
    return {"state": "invalid", "value": None, "raw": raw}


def extract(dataset, item):
    raw = item.raw_xml or ""
    result = {
        "dataset": dataset,
        "accession": item.accession_number,
        "cik": item.issuer.cik,
        "source_hash": hashlib.sha256(raw.encode()).hexdigest(),
        "source_url": f'https://www.sec.gov/Archives/edgar/data/{int(item.issuer.cik)}/{item.accession_number.replace("-", "")}/{item.accession_number}-index.htm',
        "accepted_at": None,
        "identity": {},
        "facts": {},
        "references": [],
        "issues": [],
    }
    if not raw:
        result["issues"].append(
            "Stored source document unavailable; no identity or values inferred."
        )
        return result
    if len(raw.encode()) > 5_000_000:
        result["issues"].append(
            "Source exceeds the extraction size limit; needs operator review."
        )
        return result
    stamp = re.search(r"<ACCEPTANCE-DATETIME>\s*([0-9]{14})", raw, re.I)
    if stamp:
        try:
            result["accepted_at"] = datetime.strptime(
                stamp.group(1), "%Y%m%d%H%M%S"
            ).replace(tzinfo=ZoneInfo("America/New_York"))
        except ValueError:
            result["issues"].append("Invalid SEC acceptance timestamp.")
    xml = re.search(r"<XML>\s*(.*?)\s*</XML>", raw, re.S | re.I)
    payload = xml.group(1) if xml else raw
    try:
        root = etree.fromstring(
            payload.encode(),
            parser=etree.XMLParser(
                resolve_entities=False, no_network=True, recover=False
            ),
        )
    except (etree.XMLSyntaxError, ValueError):
        result["issues"].append(
            "Source is not supported structured XML; retained for source review."
        )
        return result
    tree = root.getroottree()
    identities = {
        "entityName",
        "issuerName",
        "street1",
        "street2",
        "city",
        "stateOrCountry",
        "zipCode",
        "jurisdictionOfInc",
        "entityType",
    }
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        tag = etree.QName(el).localname
        parent = (
            etree.QName(el.getparent()).localname
            if el.getparent() is not None and isinstance(el.getparent().tag, str)
            else ""
        )
        text = (el.text or "").strip()
        if tag in identities and not len(el) and tag not in result["identity"]:
            # Only issuer identity, never recipient/person addresses.
            if any(
                etree.QName(p).localname
                in {"primaryIssuer", "issuerInformation", "issuerInfo", "issuer"}
                for p in el.iterancestors()
                if isinstance(p.tag, str)
            ):
                result["identity"][tag] = text
        key = (
            tag
            if tag in FIELDS
            else (
                parent
                if parent in FIELDS and tag in {"dollarAmount", "amount"}
                else None
            )
        )
        if key and not len(el):
            fact = numeric_state(text)
            fact.update(
                label=FIELDS[key],
                xpath=tree.getpath(el),
                units=(
                    "count"
                    if key == "totalNumberAlreadyInvested"
                    else "USD as specified by the source form"
                ),
                estimated=None,
            )
            siblings = list(el.getparent()) if el.getparent() is not None else []
            estimated = next(
                (
                    (x.text or "").strip().lower()
                    for x in siblings
                    if isinstance(x.tag, str)
                    and etree.QName(x).localname.lower()
                    in {"isestimate", "isestimated"}
                ),
                None,
            )
            if estimated is not None:
                fact["estimate_qualifier_raw"] = estimated
                fact["estimated"] = (
                    True
                    if estimated in {"true", "1", "yes"}
                    else False if estimated in {"false", "0", "no"} else None
                )
            result["facts"][key] = fact
        if (
            tag
            in {
                "federalExemption",
                "federalExemptions",
                "item",
                "typeOfPooledInvestmentFund",
                "investmentFundType",
                "isEquityType",
                "isDebtType",
                "isPooledInvestmentFundType",
            }
            and text
            and not len(el)
        ):
            if tag != "item" or any(
                name in {"federalExemptionsUsed", "federalExemptionsExclusions"}
                for name in [
                    etree.QName(p).localname
                    for p in el.iterancestors()
                    if isinstance(p.tag, str)
                ]
            ):
                result["facts"].setdefault("classifications", []).append(
                    {"field": tag, "raw": text, "xpath": tree.getpath(el)}
                )
        if (
            tag == "previousAccessionNumber"
            and re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", text)
            and text != item.accession_number
        ):
            result["references"].append(text)
    return result


def materialize(dataset, item):
    values = extract(dataset, item)
    values["source_record_updated_at"] = item.updated_at
    if not values["accepted_at"]:
        from django.db.models import BinaryField
        from django.db.models.functions import Substr
        from filings.models import IngestionSource

        headers = (
            IngestionSource.objects.filter(
                job__dataset=dataset,
                job__key=item.accession_number,
                url__endswith=item.accession_number + ".txt",
            )
            .order_by("-retrieved_at")
            .annotate(header=Substr("content", 1, 16384, output_field=BinaryField()))
            .values_list("header", flat=True)[:1]
        )
        for header in headers:
            stamp = re.search(
                rb"<ACCEPTANCE-DATETIME>\s*([0-9]{14})", bytes(header), re.I
            )
            if stamp:
                try:
                    values["accepted_at"] = datetime.strptime(
                        stamp.group(1).decode(), "%Y%m%d%H%M%S"
                    ).replace(tzinfo=ZoneInfo("America/New_York"))
                except ValueError:
                    pass
    evidence, _ = DisclosureEvidence.objects.get_or_create(
        dataset=dataset,
        accession=values.pop("accession"),
        source_hash=values.pop("source_hash"),
        extraction_version=EXTRACTION_VERSION,
        defaults={k: v for k, v in values.items() if k != "dataset"},
    )
    from django.utils import timezone

    from django.db.models import F, Value
    from django.db.models.functions import Greatest, Coalesce

    DisclosureEvidence.objects.filter(pk=evidence.pk).update(
        last_checked_at=timezone.now(),
        source_record_updated_at=Greatest(
            Coalesce(F("source_record_updated_at"), Value(item.updated_at)),
            Value(item.updated_at),
        ),
    )
    return evidence
