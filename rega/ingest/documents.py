"""Find a structured primary document without assuming an attachment name."""
import re

from requests import HTTPError

from filings.ingest.index_parser import primary_doc_url


class UnsupportedDocument(ValueError):
    pass


def primary_xml(client, entry):
    try:
        return client.get_bytes(primary_doc_url(entry.filename))
    except HTTPError as exc:
        # Permission/throttling/network failures must remain errors, not skips.
        if exc.response is None or exc.response.status_code != 404:
            raise
    # The index points to the complete submission. Its DOCUMENT TYPE identifies
    # the primary form, unlike choosing the first XML attachment or an exhibit.
    submission = client.get_bytes("/Archives/" + entry.filename)
    for document in re.findall(rb"<DOCUMENT>(.*?)</DOCUMENT>", submission, re.I | re.S):
        kind = re.search(rb"<TYPE>\s*([^\r\n<]+)", document, re.I)
        if not kind or kind.group(1).strip() != entry.form_type.encode("ascii"):
            continue
        xml = re.search(rb"<XML>\s*(.*?)\s*</XML>", document, re.I | re.S)
        if xml:
            return xml.group(1)
        text = re.search(rb"<TEXT>\s*(.*?)\s*</TEXT>", document, re.I | re.S)
        if text and re.match(rb"(?:<\?xml[^>]*>\s*)?<edgarSubmission\b", text.group(1)):
            return text.group(1)
    raise UnsupportedDocument(f"No supported structured {entry.form_type} document in {entry.filename}")
