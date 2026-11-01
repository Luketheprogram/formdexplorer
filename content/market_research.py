"""Three deliberately curated research notes from a frozen real-data snapshot.

No request-time analysis or automatic monthly publishing. The public JSON is the
single numerical source; corrections require a new reviewed snapshot/edition.
"""
import json
from decimal import Decimal
from pathlib import Path

from filings.intelligence import percent

SNAPSHOT = json.loads((Path(__file__).resolve().parents[1] / 'static/research/october-2026-snapshot.json').read_text())
CURRENT = SNAPSHOT['current']
PREVIOUS = SNAPSHOT['previous']
STAMP = SNAPSHOT['data_as_of']
METHODS = f"""## Scope and reproduction

This note uses a frozen production snapshot captured **{STAMP}**. October means filing dates October 1–31, 2026; September means September 1–30. The database's latest available filing date at capture was October 30. A completed calendar month is not a certification of complete SEC coverage. Counts may differ from the live tools after later imports or corrections.

The unit is a unique stored accession with a nonblank issuer name. Issuers are distinct stored CIKs, not brands, offerings or fund families. A record is an amendment when the submission type is D/A or its extracted amendment flag is true. Missing or negative financial fields are unavailable; zero remains a numeric observation. No offered or sold amounts are summed.

[Download the exact aggregate snapshot and definitions](/static/research/october-2026-snapshot.json). The deterministic calculation is `month_snapshot` in `filings/research_publication.py` in the [public source repository](https://github.com/Luketheprogram/formdexplorer). See [coverage](/research/coverage/), [methodology](/learn/form-d-data-methodology/), and [corrections](/editorial/) for limitations and feedback.
"""

def number(value):
    return f'{value:,}'


def change(current, previous):
    value = percent(current-previous, previous)
    return f'{value:+.1f}%' if value is not None else 'unavailable'


pooled = next(row for row in SNAPSHOT['industries'] if row['industry_group'] == 'Pooled Investment Fund')
top_five = SNAPSHOT['industries'][:5]
industry_rows = '\n'.join(f"| {row['industry_group']} | {number(row['filings'])} | {number(row['issuers'])} | {number(row['originals'])} | {number(row['amendments'])} | {row['dataset_share']}% |" for row in top_five)
coverage_rows = '\n'.join(f"| {row['label']} | {number(row['filings'])} | {number(row['offering_known'])} ({percent(row['offering_known'],row['filings'])}%) | {number(row['sold_known'])} | {number(row['investors_known'])} |" for row in SNAPSHOT['availability_by_submission'])

MARKET_RESEARCH = [
    {
        'slug': 'october-2026-form-d-filing-activity',
        'title': 'October 2026 Form D activity: more initial notices, fewer amendments',
        'meta_description': 'A frozen analysis of 5,780 stored October Form D filings: initial notices, amendments, distinct CIKs and repeat issuers, compared with September.',
        'body': f"""October's stored Form D filing count was **{number(CURRENT['filings'])}**, compared with **{number(PREVIOUS['filings'])}** in September: **{number(SNAPSHOT['filing_difference'])} more submissions ({SNAPSHOT['filing_change_percent']}%)**. Separating original notices from amendments reveals two different movements inside that total.

## What changed in the stored submission mix

| Measure | September 2026 | October 2026 | Arithmetic difference |
|---|---:|---:|---:|
| All filings | {number(PREVIOUS['filings'])} | {number(CURRENT['filings'])} | {change(CURRENT['filings'],PREVIOUS['filings'])} |
| Initial notices | {number(PREVIOUS['originals'])} | {number(CURRENT['originals'])} | {change(CURRENT['originals'],PREVIOUS['originals'])} |
| Amendments | {number(PREVIOUS['amendments'])} | {number(CURRENT['amendments'])} | {change(CURRENT['amendments'],PREVIOUS['amendments'])} |
| Distinct issuer CIKs | {number(PREVIOUS['issuers'])} | {number(CURRENT['issuers'])} | {change(CURRENT['issuers'],PREVIOUS['issuers'])} |
| Amendment share of filings | {PREVIOUS['amendment_share']}% | {CURRENT['amendment_share']}% | {Decimal(CURRENT['amendment_share'])-Decimal(PREVIOUS['amendment_share']):.1f} percentage points |

The net increase combines **{number(CURRENT['originals']-PREVIOUS['originals'])} additional initial notices** with **{number(PREVIOUS['amendments']-CURRENT['amendments'])} fewer amendments**. Calling the total a count of new financing rounds would discard that distinction. These differences describe the stored observations; they do not establish increased capital formation or cash received.

## Repeated submissions also affect the count

October contains {number(CURRENT['filings'])} accessions from {number(CURRENT['issuers'])} CIKs, a gap of **{number(CURRENT['filings']-CURRENT['issuers'])}**. Exactly **{number(CURRENT['repeat_issuer_ciks'])} CIKs** have more than one stored filing that month. The gap is not the number of repeat issuers: an issuer can contribute three or more submissions. Nor can either number identify distinct offerings without reviewing the underlying notices.

For concrete source checks, [BigHat Biosciences accession 0001231919-26-001499](https://www.sec.gov/Archives/edgar/data/1797256/000123191926001499/0001231919-26-001499-index.htm) is an October 26 initial D, while [Tenora Studios accession 0001213900-26-114364](https://www.sec.gov/Archives/edgar/data/2151144/000121390026114364/0001213900-26-114364-index.htm) is an October 30 D/A. Their primary XML submission types were checked directly. They illustrate different record types inside the count, not a relationship between the issuers.

## How to use the result

Use the [live monthly report](/research/filing-activity/) to separate notice types before comparing periods, then [compare categories](/research/compare/) using the same dates. Preserve accessions when investigating repeated issuers. Distinct CIK counts should be calculated across the desired period rather than added across months.

""" + METHODS,
    },
    {
        'slug': 'october-2026-form-d-industry-mix',
        'title': 'October 2026 industry mix: how amendments change the picture',
        'meta_description': 'Pooled Investment Fund accounts for 66.4% of stored October notices, but the mix differs between initial filings and amendments. Examine the exact denominators.',
        'body': f"""The issuer-reported **Pooled Investment Fund** category accounts for **{number(pooled['filings'])} of {number(CURRENT['filings'])} stored October filings ({pooled['dataset_share']}%)**. That headline combines initial notices and amendments. Its share is **{percent(pooled['originals'],CURRENT['originals'])}% of initial notices** and **{percent(pooled['amendments'],CURRENT['amendments'])}% of amendments**—different comparisons that answer different research questions.

## The five largest categories by stored filing count

| Issuer-reported industry | Filings | Distinct CIKs | Initial notices | Amendments | Share of all October filings |
|---|---:|---:|---:|---:|---:|
{industry_rows}

Together these five categories contain **{number(sum(row['filings'] for row in top_five))} filings ({percent(sum(row['filings'] for row in top_five),CURRENT['filings'])}%)**. This concentration concerns classified submissions in this dataset. It does not measure industry shares of capital raised, company valuations or economic investment.

## Why the denominator matters

Within Pooled Investment Fund, {number(pooled['amendments'])} of {number(pooled['filings'])} filings are amendments ({percent(pooled['amendments'],pooled['filings'])}%). A researcher counting every filing sees a different composition from someone restricting the question to initial notices. Neither view proves that one sector attracted more money; an amendment may repeat an earlier disclosure.

Distinct issuer counts help assess repetition, but are not interchangeable with offering counts. A CIK can also appear in more than one industry when its filing classifications differ. Adding the category CIK counts may therefore count a filer twice. The share column uses all {number(CURRENT['filings'])} eligible October accessions as its denominator, including records outside these five categories.

## A repeatable industry comparison

Use the [industry directory](/industries/) to open a category and inspect the underlying issuers. The [comparison tool](/research/compare/?kind=industry) aligns the calendar windows for two categories. Compare initial notices and amendments separately before interpreting an apparent difference in activity.

Industry is the selection recorded on each notice, not an independently verified business classification. For example, the [SEC primary disclosure for BigHat Biosciences](https://www.sec.gov/Archives/edgar/data/1797256/000123191926001499/primary_doc.xml) selects Biotechnology. It supplies a traceable example of classification; it does not validate the classification of every record or establish the firm's investment merits.

A useful research note states both the scope and the denominator: “share of stored October filings” is reproducible here. A claim about the private market as a whole would require a separately validated coverage universe and appropriate financial measures.

""" + METHODS,
    },
    {
        'slug': 'october-2026-form-d-disclosure-coverage',
        'title': 'October 2026 disclosure coverage: what an offering-size filter leaves out',
        'meta_description': 'Only 3,114 of 5,780 stored October filings contain a usable numeric offering amount. Examine missing fields, amendment selection and reported zeros.',
        'body': f"""A filter requiring a usable numeric offering amount retains **{number(CURRENT['offering_known'])} of {number(CURRENT['filings'])} October records ({percent(CURRENT['offering_known'],CURRENT['filings'])}%)**. It excludes **{number(CURRENT['filings']-CURRENT['offering_known'])} records ({percent(CURRENT['filings']-CURRENT['offering_known'],CURRENT['filings'])}%)**. This is a material change in the research sample before any offering-size threshold is applied.

## Availability differs between notice types

“Usable” below means a nonnegative number stored in the field, including zero. It does not mean the original disclosure has been independently certified.

| Submission class | Records | Numeric offering amount | Numeric amount sold | Numeric investor count |
|---|---:|---:|---:|---:|
{coverage_rows}

The offering-amount field is numeric in {percent(SNAPSHOT['availability_by_submission'][0]['offering_known'],CURRENT['originals'])}% of initial notices, versus {percent(SNAPSHOT['availability_by_submission'][1]['offering_known'],CURRENT['amendments'])}% of amendments. Requiring that field therefore changes the submission mix as well as reducing the sample. A filtered offering-size analysis should disclose this selection, rather than present the retained rows as the full month.

Unavailable numbers can reflect an indefinite source amount, an absent value or an extraction limitation. The stored blank alone does not identify the cause. Open the SEC source before assigning one, and do not convert the blank to zero.

## Numeric zero is a different observation

October includes **{number(CURRENT['sold_zero'])} records with reported amount sold stored as zero ({percent(CURRENT['sold_zero'],CURRENT['filings'])}%)**, and **{number(CURRENT['investors_zero'])} with investor count stored as zero**. These records remain numeric for availability purposes. The counts concern fields, not a verified number of unsuccessful offerings. A zero disclosure does not establish an issuer's lifetime proceeds or current financing status.

Both amount sold and investor count are numeric in all {number(CURRENT['filings'])} stored October records. That is a description of database values, not proof that the dataset contains every SEC filing or that every extracted value is correct.

## Two checked source examples

[BigHat's October 26 disclosure](https://www.sec.gov/Archives/edgar/data/1797256/000123191926001499/primary_doc.xml) reports $79,999,947 offered, $75,141,086 sold and 29 investors. [Tenora's October 30 amendment](https://www.sec.gov/Archives/edgar/data/2151144/000121390026114364/primary_doc.xml) reports $10,000,000 offered, $1,500,000 sold and 14 investors. These fields, submission types and CIKs were checked against the original SEC XML. They are separate issuers, not an amendment chain or a combined fundraising total.

Use the [field interpretation guide](/learn/form-d-offering-amount-vs-amount-sold/) before calculating with amounts. For an issuer-specific question, the [change viewer](/research/filing-changes/) preserves missing values and shows source links; it does not certify that two filings concern one offering.

""" + METHODS,
    },
]
