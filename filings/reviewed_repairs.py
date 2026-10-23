"""Guarded application of the explicitly reviewed C3 repair bundle.

Called by the operator only after source/manifest validation and a fresh backup.
This never fetches SEC data, merges issuers, or edits original filing rows.
"""
import hashlib
import json
from datetime import date
from urllib.parse import urlparse

from django.db import transaction

from filings.models import Issuer, IssuerIdentityReview, normalize_issuer_name
from rega.models import Form1AFiling, RegAFilingReview


def canonical(value):
    return json.loads(json.dumps(value, default=str, sort_keys=True))


def issuer_snapshot(issuer):
    return canonical({f.attname: getattr(issuer, f.attname) for f in issuer._meta.concrete_fields})


def filing_snapshot(filing):
    values = {f.attname: getattr(filing, f.attname) for f in filing._meta.concrete_fields}
    raw = values.pop("raw_xml").encode()
    return canonical({**values, "dataset": "rega", "source_xml_bytes": len(raw),
                      "source_xml_sha256": hashlib.sha256(raw).hexdigest()})


def _sources(sources):
    if not sources:
        raise ValueError("Missing SEC source evidence")
    for source in sources:
        url = urlparse(source["url"])
        if url.scheme != "https" or url.netloc not in {"www.sec.gov", "data.sec.gov"}:
            raise ValueError("Expected original SEC source")
        if len(source["sha256"]) != 64 or source["status"] != 200:
            raise ValueError("Invalid source receipt")
    return sources


@transaction.atomic
def apply_c3_review(plan, snapshots):
    updates = plan["recommended_bundle"]["existing_field_updates"]
    if len(updates) != 1:
        raise ValueError("Expected one reviewed issuer")
    update = updates[0]
    if update["pk"] != 24219 or update["cik"] != "1827424" or update["after"] != {
        "name": "C3 Capital, Inc.", "normalized_name": normalize_issuer_name("C3 Capital, Inc.")
    }:
        raise ValueError("Unexpected C3 identity scope")
    expected = {r["issuer"]["id"]: r for r in snapshots}
    if set(expected) != {24218, 24219}:
        raise ValueError("Expected both distinct C3 snapshots")
    issuers = {i.pk: i for i in Issuer.objects.select_for_update().filter(pk__in=expected).order_by("pk")}
    for pk, snapshot in expected.items():
        if pk not in issuers or issuer_snapshot(issuers[pk]) != snapshot["issuer"]:
            raise ValueError("Issuer snapshot drift or repeated application")
        if snapshot["url"] != "https://formdexplorer.com/issuer/" + issuers[pk].url_slug + "/":
            raise ValueError("Issuer URL drift")
    original_filings = {f["id"]: f for r in snapshots for f in r["filings"]}
    filings = {f.pk: f for f in Form1AFiling.objects.select_for_update().filter(
        issuer_id__in=expected).order_by("pk")}
    if {pk: filing_snapshot(f) for pk, f in filings.items()} != original_filings:
        raise ValueError("Original filing/source drift")
    identity, first = plan["recommended_bundle"]["new_review_records"]
    second, = plan["additional_reviewed_option"]["new_review_records"]
    if identity["issuer_id"] != 24219 or identity["related_distinct_issuer_id"] != 24218:
        raise ValueError("Unexpected identity association")
    if identity["historical_name"] != update["after"]["name"]:
        raise ValueError("Historical name mismatch")
    expected_events = {(1159, "0001827424-23-000007", "1827424", "024-12366", "0001827424-23-000011", "2023-12-05"),
                       (1218, "0001981779-24-000001", "1981779", "024-12387", "0001981779-24-000003", "2024-01-17")}
    events = (first, second)
    if {tuple(r[k] for k in ("filing_id", "target_accession", "target_cik", "offering_file_number", "withdrawal_accession", "withdrawal_filed_date")) for r in events} != expected_events:
        raise ValueError("Withdrawal target or offering mismatch")
    if update["url_before"] != update["url_after"] or update["url_before"] != expected[24219]["url"]:
        raise ValueError("URL change not authorized")
    count = Issuer.objects.filter(pk=24219, cik="1827424", name_slug=update["name_slug_preserved"],
                                  **update["before"]).update(**update["after"])
    if count != 1:
        raise ValueError("Expected exactly one unchanged before-value")
    IssuerIdentityReview.objects.create(
        key=identity["key"], issuer_id=24219, historical_name=identity["historical_name"],
        sec_profile_name=identity["sec_profile_name"], related_distinct_issuer_id=24218,
        note=identity["note"], sources=_sources(identity["sources"]),
    )
    for event in events:
        if event["status"] != "withdrawal_filed" or not event["source_reported_only"]:
            raise ValueError("Only a source-reported withdrawal event is approved")
        review = RegAFilingReview(
            **{k: event[k] for k in ("key", "filing_id", "target_accession", "target_cik",
                "offering_file_number", "status", "withdrawal_accession", "note")},
            withdrawal_filed_date=date.fromisoformat(event["withdrawal_filed_date"]),
            sources=_sources(event["sources"]),
        )
        review.full_clean()
        review.save(force_insert=True)
    for pk, issuer in issuers.items():
        issuer.refresh_from_db()
        wanted = {**expected[pk]["issuer"], **(update["after"] if pk == 24219 else {})}
        if issuer_snapshot(issuer) != wanted:
            raise ValueError("Unexpected issuer column changed")
    if {f.pk: filing_snapshot(f) for f in Form1AFiling.objects.filter(pk__in=filings)} != original_filings:
        raise ValueError("Original filing changed")
    return {"issuer_fields_updated": 2, "identity_reviews_created": 1, "withdrawal_reviews_created": 2}
