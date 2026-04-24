"""Parse EDGAR daily-index form.idx files for Form D / D/A entries."""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class IndexEntry:
    form_type: str
    company: str
    cik: str
    filing_date: str  # YYYY-MM-DD
    filename: str     # e.g. edgar/data/1234/0001234-56-000001.txt


def daily_index_paths(d: date) -> list[str]:
    q = (d.month - 1) // 3 + 1
    # form.idx is sorted by form type — efficient for Form D filtering.
    return [
        f"/Archives/edgar/daily-index/{d.year}/QTR{q}/form.{d.strftime('%Y%m%d')}.idx",
    ]


def iter_business_days(start: date, end: date):
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            yield cur
        cur += timedelta(days=1)


def parse_form_idx(text: str) -> list[IndexEntry]:
    """Parse a form.idx file. Fixed-width; header ends with a line of dashes."""
    lines = text.splitlines()
    data_start = 0
    for i, line in enumerate(lines):
        if line.startswith("----"):
            data_start = i + 1
            break
    # Column positions derived from EDGAR's standard form.idx layout.
    # Form Type (12) | Company Name (62) | CIK (12) | Date Filed (12) | Filename
    entries = []
    for line in lines[data_start:]:
        if not line.strip():
            continue
        form_type = line[0:12].strip()
        if form_type not in ("D", "D/A"):
            continue
        company = line[12:74].strip()
        cik = line[74:86].strip()
        date_filed = line[86:98].strip()
        filename = line[98:].strip()
        entries.append(
            IndexEntry(
                form_type=form_type,
                company=company,
                cik=cik,
                filing_date=date_filed,
                filename=filename,
            )
        )
    return entries


def primary_doc_url(filename: str) -> str:
    """Given 'edgar/data/1234/0001234-56-000001.txt', return primary_doc.xml URL.

    Form D is XML-only and lives at the accession folder as primary_doc.xml.
    """
    # filename: edgar/data/<cik>/<accession-with-dashes>.txt
    path_no_ext = filename[: -len(".txt")] if filename.endswith(".txt") else filename
    parts = path_no_ext.rsplit("/", 1)
    folder_path = parts[0]
    accession_with_dashes = parts[1]
    accession_no_dashes = accession_with_dashes.replace("-", "")
    return f"/Archives/{folder_path}/{accession_no_dashes}/primary_doc.xml"


def accession_from_filename(filename: str) -> str:
    path_no_ext = filename[: -len(".txt")] if filename.endswith(".txt") else filename
    return path_no_ext.rsplit("/", 1)[1]
