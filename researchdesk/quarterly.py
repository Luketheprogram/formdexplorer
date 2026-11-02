"""Compare SEC quarterly accession manifests without changing filing records.

SEC quarterly postings can contain filings from the preceding quarter after its
last-day cutoff. A manifest comparison is therefore not daily completeness.
"""

import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import date, datetime

from django.db.models import Min, Max
from django.utils import timezone

from filings.models import Filing

SOURCE_PAGE = "https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets"
DOCUMENTATION = "https://www.sec.gov/files/Form_D.pdf"


def parse_manifest(payload):
    if len(payload) > 20 * 1024 * 1024:
        raise ValueError("Quarterly archive exceeds 20 MiB.")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        files = archive.infolist()
        if len(files) > 30 or sum(f.file_size for f in files) > 150 * 1024 * 1024:
            raise ValueError("Quarterly archive exceeds extraction limits.")
        candidates = [
            f
            for f in files
            if f.filename.rsplit("/", 1)[-1].upper()
            in {"FORMDSUBMISSION.TSV", "FORMDSUBMISSION.TXT"}
        ]
        if len(candidates) != 1:
            raise ValueError("Exactly one FORMDSUBMISSION table is required.")
        with archive.open(candidates[0]) as stream:
            reader = csv.DictReader(
                io.TextIOWrapper(stream, encoding="utf-8-sig"), delimiter="\t"
            )
            if not {"ACCESSIONNUMBER", "FILING_DATE", "SUBMISSIONTYPE"}.issubset(
                reader.fieldnames or []
            ):
                raise ValueError(
                    "Quarterly submission headers do not match SEC documentation."
                )
            entries = {}
            for row in reader:
                accession = row["ACCESSIONNUMBER"].strip()
                if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
                    raise ValueError(
                        "Invalid quarterly accession; no coverage certification made."
                    )
                if row["SUBMISSIONTYPE"].strip() not in {"D", "D/A"}:
                    raise ValueError("Unexpected submission type in Form D manifest.")
                raw = row["FILING_DATE"].strip()
                filed = None
                for fmt in ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d"):
                    try:
                        filed = datetime.strptime(raw, fmt).date()
                        break
                    except ValueError:
                        pass
                if filed is None:
                    raise ValueError("Unrecognized filing date; no date is inferred.")
                if accession in entries:
                    raise ValueError("Duplicate accession in quarterly manifest.")
                entries[accession] = filed
                if len(entries) > 100000:
                    raise ValueError("Quarterly manifest exceeds the row limit.")
    if not entries:
        raise ValueError("An empty manifest cannot establish completeness.")
    return entries


def compare_manifest(payload, source_url):
    expected = parse_manifest(payload)
    stored_dates = dict(
        Filing.objects.filter(accession_number__in=expected).values_list(
            "accession_number", "filing_date"
        )
    )
    stored = set(stored_dates)
    mismatches = [
        {
            "accession": acc,
            "stored_filing_date": stored_dates[acc].isoformat(),
            "sec_filing_date": expected[acc].isoformat(),
        }
        for acc in sorted(stored)
        if stored_dates[acc] != expected[acc]
    ]
    missing = sorted(set(expected) - stored)
    return {
        "source_url": source_url,
        "source_page": SOURCE_PAGE,
        "documentation": DOCUMENTATION,
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "checked_at": timezone.now().isoformat(),
        "expected": len(expected),
        "matched": len(stored),
        "missing": missing,
        "filing_date_mismatches": mismatches,
        "first_manifest_filing_date": min(expected.values()).isoformat(),
        "last_manifest_filing_date": max(expected.values()).isoformat(),
        "status": "matched_manifest" if not missing else "partial",
        "limitations": "Compares exact accessions in this quarterly posting only. Late final-day filings may appear in the subsequent posting. This does not establish daily or market completeness. No filing is created, removed or merged.",
    }
