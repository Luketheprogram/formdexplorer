"""Identify the primary form, never an exhibit or an error page."""
import re
from dataclasses import dataclass

from lxml import etree
from requests import HTTPError

from filings.ingest.index_parser import primary_doc_url, accession_from_filename


class UnsupportedDocument(ValueError):
    pass


@dataclass
class PrimaryDocument:
    content: bytes
    structured: bool


def validate_xml(content, *, required_tag=None, expected_form=None):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    root = etree.fromstring(content, parser)
    if etree.QName(root).localname != "edgarSubmission":
        raise UnsupportedDocument("Primary document is not an EDGAR submission")
    if required_tag and not root.xpath(f".//*[local-name()='{required_tag}']"):
        raise UnsupportedDocument(f"Unrecognized XML schema: missing {required_tag}")
    forms = root.xpath(".//*[local-name()='submissionType']/text()")
    if expected_form and forms and any(form.strip() != expected_form for form in forms):
        raise UnsupportedDocument("XML submission type disagrees with the SEC index")
    return content


def primary_document(client, entry):
    try:
        return PrimaryDocument(validate_xml(client.get_bytes(primary_doc_url(entry.filename))), True)
    except HTTPError as exc:
        if exc.response is None or exc.response.status_code != 404:
            raise
    submission = client.get_bytes("/Archives/" + entry.filename)
    for document in re.findall(rb"<DOCUMENT>(.*?)</DOCUMENT>", submission, re.I | re.S):
        kind = re.search(rb"<TYPE>\s*([^\r\n<]+)", document, re.I)
        if not kind or kind.group(1).strip() != entry.form_type.encode("ascii"):
            continue
        xml = re.search(rb"<XML>\s*(.*?)\s*</XML>", document, re.I | re.S)
        if xml:
            return PrimaryDocument(validate_xml(xml.group(1)), True)
        text = re.search(rb"<TEXT>\s*(.*?)\s*</TEXT>", document, re.I | re.S)
        if not text or not text.group(1).strip():
            continue
        content = text.group(1)
        if re.match(rb"(?:<\?xml[^>]*>\s*)?<edgarSubmission\b", content):
            return PrimaryDocument(validate_xml(content), True)
        # HTML/text contributes only independently validated filing metadata. The
        # full original submission is archived by RecordingClient. Require the
        # SEC header accession and issuer CIK; index company names aren't legal-
        # name authority and must never overwrite an existing shared issuer.
        header = submission.split(b"<DOCUMENT>", 1)[0]
        accession = re.search(rb"ACCESSION NUMBER:\s*([\d-]+)", header)
        cik = re.search(rb"CENTRAL INDEX KEY:\s*(\d+)", header)
        form = re.search(rb"CONFORMED SUBMISSION TYPE:\s*([^\r\n]+)", header)
        filed = re.search(rb"FILED AS OF DATE:\s*(\d{8})", header)
        if (not accession or accession.group(1).decode() != accession_from_filename(entry.filename)
                or not cik or cik.group(1).decode().lstrip("0") != entry.cik.lstrip("0")
                or not form or form.group(1).strip().decode() != entry.form_type
                or not filed or filed.group(1).decode() != entry.filing_date.replace("-", "")):
            raise UnsupportedDocument("Unstructured submission header/index mismatch")
        return PrimaryDocument(content, False)
    raise UnsupportedDocument(f"No supported primary {entry.form_type} document in {entry.filename}")


def primary_xml(client, entry):
    document = primary_document(client, entry)
    if not document.structured:
        raise UnsupportedDocument("Primary document is unstructured")
    return document.content
