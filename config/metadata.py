"""Formatting for HTML and social metadata; visible headings remain independent."""

from django.utils.text import Truncator

SITE_NAME = "Form D Explorer"
DEFAULT_TITLE = f"SEC Form D Filings & Private Placement Database | {SITE_NAME}"
DEFAULT_DESCRIPTION = (
    "Explore SEC Form D filings in a searchable private placement database. "
    "Research issuers, reported offering amounts, industries, and filing history."
)


def clean_text(value):
    # Ordinary text: Django still escapes quotes, ampersands and markup.
    return " ".join(str(value or "").split())


def short_name(value):
    # Bound only the name, retaining record identifiers for uniqueness.
    return Truncator(clean_text(value)).chars(70)


def metadata(title, description, *, page=None):
    title = clean_text(title)
    for separator in (" | ", " — ", " - "):
        suffix = separator + SITE_NAME
        if title.endswith(suffix):
            title = title[:-len(suffix)]
            break
    description = clean_text(description)
    if page is not None and page.number > 1:
        title += f" — Page {page.number}"
        description = f"Page {page.number}. {description}"
    return {
        "page_title": f"{title} | {SITE_NAME}",
        "meta_description": description,
    }


def filing_metadata(filing, summary):
    name = short_name(filing.issuer.name)
    form = clean_text(filing.form_type)
    accession = filing.accession_number
    filed = filing.filing_date.isoformat()
    return metadata(
        f"{name} — SEC Form {form}, {filed} ({accession})",
        f"{name}: SEC Form {form} filed {filed}, accession {accession}. {summary}",
    )
