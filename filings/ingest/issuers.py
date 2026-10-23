"""Conservative shared-issuer updates across the three filing pipelines."""
import hashlib
import json

from django.db import transaction
from django.db.models import Max

from filings.models import Issuer, IssuerIdentityReview, IssuerIdentityObservation, IssuerFieldReview, IssuerFieldObservation


@transaction.atomic
def upsert_issuer(parsed, filing_date, accession_number=""):
    cik = parsed.cik.strip().lstrip("0")
    if not cik or not cik.isascii() or not cik.isdigit() or len(cik) > 10:
        raise ValueError("Missing or invalid issuer CIK")
    issuer, created = Issuer.objects.select_for_update().get_or_create(
        cik=cik, defaults={"name": (parsed.name.strip() or f"CIK {cik}")[:255]},
    )
    review = IssuerIdentityReview.objects.filter(issuer=issuer).first()
    if review:
        # The issuer row lock serializes this check with review application.
        # Keep all reviewed identity columns and URL components stable. Retain
        # incoming values separately, including blanks, without changing sources.
        values = {field: getattr(parsed, field) for field in (
            "cik", "name", "entity_type", "jurisdiction", "year_of_incorporation",
            "street", "city", "state", "zip_code", "phone",
        )}
        payload = json.dumps([issuer.pk, accession_number, str(filing_date), values], sort_keys=True)
        IssuerIdentityObservation.objects.get_or_create(
            fingerprint=hashlib.sha256(payload.encode()).hexdigest(),
            defaults={"review": review, "accession_number": accession_number,
                      "filing_date": filing_date, "source_values": values},
        )
        return issuer
    field_reviews = {r.field_name: r for r in IssuerFieldReview.objects.filter(issuer=issuer)}
    for field, field_review in field_reviews.items():
        value = getattr(parsed, field)
        payload = json.dumps([field_review.pk, accession_number, str(filing_date), value])
        IssuerFieldObservation.objects.get_or_create(
            fingerprint=hashlib.sha256(payload.encode()).hexdigest(),
            defaults={"review": field_review, "accession_number": accession_number,
                      "filing_date": filing_date, "source_value": value},
        )
        setattr(issuer, field, field_review.reviewed_value)
    # For pre-migration records, derive a conservative baseline from existing
    # filings instead of letting the first historical replay become current.
    latest = issuer.source_filing_date
    if latest is None and not created:
        dates = [manager.aggregate(latest=Max("filing_date"))["latest"] for manager in
                 (issuer.filings, issuer.crowdfunding_filings, issuer.rega_filings)]
        latest = max((d for d in dates if d is not None), default=None)
    incoming_is_current = filing_date is not None and (latest is None or filing_date >= latest)
    for field in ("name", "entity_type", "jurisdiction", "year_of_incorporation",
                  "street", "city", "state", "zip_code", "phone"):
        if field in field_reviews:
            continue
        value = getattr(parsed, field).strip()
        if not value or (field == "name" and value.upper().startswith("CIK ")):
            continue
        current = getattr(issuer, field)
        missing = not current or (field == "name" and current.upper().startswith("CIK "))
        if created or missing or incoming_is_current:
            max_length = Issuer._meta.get_field(field).max_length
            setattr(issuer, field, value[:max_length])
    issuer.source_filing_date = max((d for d in (latest, filing_date) if d is not None), default=None)
    # Never regenerate a populated slug: data repairs must not move URLs.
    issuer.save()
    return issuer
