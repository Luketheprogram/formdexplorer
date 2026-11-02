"""Source-linked educational tools. Exercises never imply investment merit."""

from django.db.models import F
from filings.models import Filing
from .views import page

SOURCE = "https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets"
TERMS = [
    (
        "Accession number",
        "The SEC identifier for a particular submission. It identifies a document event, not an issuer or financing round.",
    ),
    (
        "CIK",
        "The SEC identifier for a filer. One filer can submit notices for multiple offerings.",
    ),
    (
        "Initial notice",
        "A stored notice classified as an original submission, rather than an amendment.",
    ),
    (
        "Amendment",
        "A later submission that changes or updates an earlier notice. It can repeat previously disclosed amounts.",
    ),
    (
        "Offering amount",
        "The offering size reported in a disclosure; it is not proof that this amount was received.",
    ),
    (
        "Amount sold",
        "The amount reported sold as of the disclosure. It is not independently verified cash received.",
    ),
    (
        "Indefinite amount",
        "An explicit source value that does not supply a finite numeric offering size.",
    ),
    (
        "Missing value",
        "A field unavailable in the stored observation. Missing values are not numeric zero.",
    ),
    (
        "Reported zero",
        "An explicit numeric zero. It remains distinct from an empty or undisclosed field.",
    ),
    (
        "Investor count",
        "A count reported on a particular disclosure, with the same source and timing limitations as other fields.",
    ),
    (
        "Minimum investment",
        "A minimum amount reported for an investor. It is not an average investor contribution.",
    ),
    (
        "Sales commission",
        "Compensation disclosed for sales activity; preserve any source estimate qualifier.",
    ),
    (
        "Finder fee",
        "A separately reported compensation field. Its availability and meaning come from the source notice.",
    ),
    (
        "Exemption",
        "A provision identified by the filer. Displaying it does not independently establish legal compliance.",
    ),
    (
        "Pooled Investment Fund",
        "An issuer-reported industry category, rather than an independent classification of investment merit.",
    ),
    (
        "Business address",
        "The address supplied for the issuer; it does not establish investor residence or where capital is deployed.",
    ),
    (
        "Jurisdiction",
        "A reported legal jurisdiction, which can differ from the business address.",
    ),
    (
        "Form C",
        "A crowdfunding disclosure family. Initial notices, amendments and reports are different submission types.",
    ),
    (
        "Regulation A filing",
        "A submission in the Reg A disclosure family. Its filing alone does not establish qualification or successful fundraising.",
    ),
    (
        "Form ADV",
        "Investment adviser disclosures. Reported regulatory assets under management are not Form D offering proceeds.",
    ),
    (
        "Source snapshot",
        "A retained set of inputs and definitions used to reproduce a particular calculation.",
    ),
    (
        "Coverage",
        "Which records are stored and checked against a defined source universe. Earliest and latest dates alone do not prove completeness.",
    ),
    (
        "Median",
        "The midpoint of usable observations. It describes the selected sample, including the stated missing-data exclusions.",
    ),
    (
        "Percentage point",
        "The arithmetic difference between two percentages, distinct from percentage change.",
    ),
    (
        "Distinct issuer count",
        "The number of unique stored CIKs. Counts across groups or months cannot always be added without duplication.",
    ),
]


def glossary(request):
    q = request.GET.get("q", "").strip()[:100]
    terms = [
        {"term": term, "definition": definition, "source": SOURCE}
        for term, definition in TERMS
        if not q or q.casefold() in (term + " " + definition).casefold()
    ]
    return page(request, "glossary.html", "SEC disclosure glossary", terms=terms, q=q)


def walkthrough(request):
    sample = (
        Filing.objects.select_related("issuer")
        .exclude(raw_xml="")
        .order_by("-filing_date", "-accession_number")
        .first()
    )
    return page(
        request, "walkthrough.html", "Read a real Form D disclosure", sample=sample
    )


def exercises(request):
    sample = (
        Filing.objects.select_related("issuer")
        .filter(total_offering_amount__gte=0, total_amount_sold__gte=0)
        .exclude(total_offering_amount=F("total_amount_sold"))
        .defer("raw_xml")
        .order_by("-filing_date", "-accession_number")
        .first()
    )
    return page(
        request,
        "exercises.html",
        "Practice interpreting SEC disclosures",
        sample=sample,
    )


def fields(request):
    rows = [
        (
            "Accession number",
            "Form D, C and Reg A",
            "Identifies one submission, including an amendment; it is not an offering or issuer identifier.",
        ),
        (
            "CIK",
            "Issuer disclosures",
            "The filer identifier. Similar names with different CIKs remain separate.",
        ),
        (
            "Filing date",
            "Issuer disclosures",
            "The SEC index filing date. Same-day ordering does not establish a sequence without acceptance metadata.",
        ),
        (
            "Acceptance timestamp",
            "Source evidence",
            "A source SEC acceptance timestamp when actually preserved; never inferred from a filing date.",
        ),
        (
            "Offering amount",
            "Form D",
            "Reported total offering size in source USD; indefinite, absent and invalid text remain separate value states.",
        ),
        (
            "Amount sold",
            "Form D",
            "Reported amount sold as of that disclosure, not independently verified cash. Amendments may repeat prior figures.",
        ),
        (
            "Minimum investment",
            "Form D",
            "Source-reported USD minimum, not an average contribution or investment recommendation.",
        ),
        (
            "Investor count",
            "Form D",
            "A count reported in one disclosure; counts across amendments are not summed.",
        ),
        (
            "Commissions and finder fees",
            "Source evidence",
            "Separate source compensation fields; an estimate qualifier is retained when present.",
        ),
        (
            "Maximum offering amount",
            "Form C",
            "The maximum reported offering amount when extracted. Availability varies across submission types and source schemas.",
        ),
        (
            "Offering amount and tier",
            "Reg A",
            "As extracted from the source offering statement. A filing or stated tier does not establish SEC qualification or completed sales.",
        ),
        (
            "Regulatory AUM",
            "Form ADV",
            "Reported regulatory assets under management in USD, not a capital raise, revenue measure or client return.",
        ),
        (
            "CRD / SEC identifier",
            "Form ADV",
            "The firm identifier actually stored. An SEC identifier is not substituted into a CRD-based IAPD link.",
        ),
        (
            "State / business address",
            "Issuer profile",
            "Current stored business address; not investor residence, capital deployment or historical location. Individual source evidence retains available historical addresses.",
        ),
        (
            "Industry and fund type",
            "Form D",
            "Issuer-reported classifications. They are not independent business-model or investment-quality assessments.",
        ),
        (
            "Estimated / approximate",
            "Source evidence",
            "A qualifier taken from the original field when available, separate from its numeric value.",
        ),
        (
            "Document status",
            "Source evidence",
            "Stored, unsupported, missing or awaiting review describes extraction availability, not filing validity.",
        ),
    ]
    return page(request, "fields.html", "Field dictionary", fields=rows)
