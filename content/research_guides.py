"""Practical research guides sourced from primary SEC material and our data model."""
RESEARCH_GUIDES = [
    {
        "slug": "form-d-offering-amount-vs-amount-sold",
        "title": "Form D offering amount vs. amount sold: avoid double counting",
        "meta_description": "Distinguish offering amounts, reported sales, and amendments in Form D. Use a worked example to avoid overstating an issuer's fundraising.",
        "body": """A number on a Form D is a disclosure with a date and a field name. Before putting it into a spreadsheet or a research note, record all three.

## Two fields, two different questions

Item 13 of [the SEC's Form D and instructions](https://www.sec.gov/files/formd.pdf) distinguishes the size of the offering from securities sold as of the filing date. The instructions include noncash consideration and mandatory future capital commitments in the amounts. Consequently, reported sales should not automatically be described as cash received today.

In Form D Explorer, **reported offering amount** corresponds to `total_offering_amount`; **reported amount sold** corresponds to `total_amount_sold`. Open the individual filing to see both alongside its date and accession number. A blank amount is shown as a dash. That means the database does not hold a usable numeric value, not that the issuer reported zero.

## A worked example: two records are not two raises

Consider a hypothetical original notice showing $10 million offered and $2 million sold. A later amendment shows $10 million offered and $3 million sold for that same offering. Adding the rows produces $20 million offered and $5 million sold, even though the later disclosure reports $3 million sold for the offering.

The apparent $1 million change is useful only after confirming that these records concern the same offering and that no correction explains the difference. It is not automatically a new funding round or a cash receipt during the interval. Form D Explorer currently groups histories by issuer; it does not establish offering-level amendment chains.

## A repeatable reading workflow

1. Start with the [issuer search](/search/) and confirm the legal entity using its CIK.
2. Open a filing and record its accession number, form type and filing date.
3. Copy the offering amount and amount sold into separate columns. Keep missing values blank and reported zero values as zero.
4. Open the SEC source link. Check the original filing's context and explanatory text rather than relying only on extracted fields.
5. Compare amendments before describing a change. If offering identity is uncertain, report the individual disclosures separately.
6. Save your source URLs and the date you reviewed them so another researcher can reproduce the observation.

## What these figures cannot establish

A filing amount alone does not establish valuation, revenue, investment performance, current availability, or an investor's return. Issuer-level histories can contain several offerings. A recent filing date is not proof that a transaction just closed.

We therefore show [filing activity by state](/states/) and [industry](/industries/) as counts, and show an issuer's latest available filing as a snapshot. We do not sum every row into lifetime capital raised. See our [data methodology](/learn/form-d-data-methodology/) and [issuer-history workflow](/learn/research-company-form-d-history/) before building an aggregate analysis.
""",
    },
    {
        "slug": "research-company-form-d-history",
        "title": "How to research a company's Form D filing history",
        "meta_description": "Find a company's Form D history, verify its CIK, compare notices and amendments, and preserve SEC source links for reproducible research.",
        "body": """A useful company research note starts with the correct legal entity and ends with traceable source records. This workflow uses Form D Explorer to organize the records and SEC EDGAR to verify them.

## 1. Find the legal issuer

Enter part of the company or fund name in [Form D search](/search/). Try a distinctive name fragment when a brand name produces no match. The [SEC's CIK lookup guidance](https://www.sec.gov/search-filings/cik-lookup) explains that a Central Index Key identifies a filer and that names may appear in unexpected or abbreviated forms.

Open the issuer profile and record the CIK. Compare the name and address with your research subject. Similar names are leads to investigate, not proof that two entities are the same. A fund, its manager, a portfolio company and a special-purpose vehicle may be different legal entities. Form D Explorer labels name-based suggestions separately from records joined by an issuer identifier.

## 2. Read the available history

The issuer profile shows the date range of records available in this database, original-notice and amendment counts, and a paginated filing list. These are database coverage indicators, not a promise of complete lifetime history. Open older pages when needed; do not assume the first page contains everything.

Use a simple research log with one row per accession number: CIK, form type, filing date, reported offering amount, reported amount sold, source URL and your observation. Keeping the accession number makes duplicate rows easier to identify when combining exports.

## 3. Separate submissions from economic events

A D/A is an amended notice. Multiple filings do not necessarily represent multiple funding rounds. Our list of other filings from the same issuer is a navigation aid; it does not certify an amendment chain. Compare the original SEC documents before associating records with a particular offering.

Do not add every amount in the list. The [amount interpretation guide](/learn/form-d-offering-amount-vs-amount-sold/) provides a worked example and explains why missing data must remain distinct from zero.

## 4. Add context without assuming identity

Follow the industry and state links to see other records in those categories. Industry classification is self-reported in filings; location reflects the stored issuer business address. Neither establishes where investors are based or where capital is deployed.

If an adviser match appears, verify its CRD and source record using [Form ADV search](/adv/) and the linked IAPD record. A similar manager name is not sufficient evidence of ownership, control, or an advisory relationship.

## 5. Verify and preserve the sources

Follow each filing's SEC EDGAR link and compare the fields relevant to your question. [SEC access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) explains public access and notes that records can be corrected or removed. Record the review date and keep your conclusions tied to the version you examined.

For repeat research, sign in to follow an issuer or save a filtered search. Export controls are available from the search tool subject to the existing export plan. Start with [recent disclosures](/recent/) for discovery, and read the [coverage methodology](/learn/form-d-data-methodology/) before calling a dataset complete.
""",
    },
    {
        "slug": "form-d-data-methodology",
        "title": "Form D Explorer data coverage and research methodology",
        "meta_description": "Understand Form D Explorer's SEC sources, issuer identifiers, filing counts, missing amounts, amendment limitations, and dataset coverage.",
        "body": """Form D Explorer organizes public SEC disclosures for research. It is an independent service, not the SEC, and a filing is not an endorsement of an investment. This page explains what our displays measure and where the data needs further verification.

## Sources and update process

Our Form D ingestion jobs read EDGAR filing indexes, retrieve filing XML, and store extracted records in the application database. The website reads that database; a page request does not download the SEC filing again. [The SEC describes its indexes, public access, and correction process here](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

A scheduled import is not a guarantee of instant or complete coverage. Backfills, upstream availability and parsing failures can affect which records are present. A profile's earliest and latest filing dates describe the records currently available here. They do not establish the issuer's first-ever offering or prove that every intervening filing is present. Verify completeness in EDGAR when it matters to your research.

## What counts as an issuer or filing

We identify Form D issuers by CIK and filings by accession number. Distinct-issuer counts count CIKs, not brands, fund families or economic ownership groups. Filing counts include original notices and amendments. Original notices are not labeled as completed funding rounds. Form-type counts depend on extracted classifications; some historical records may require correction. Verify a record's submission type against EDGAR before using amendment counts in an analysis.

An issuer profile can link to Form C and Regulation A records stored against the same issuer. Suggested Form ADV relationships and similar issuer names are approximate matches requiring independent verification. Name similarity does not establish identity or control.

## Geographic and industry classification

State pages use the issuer's stored business address. Issuer attributes can change when later records are imported, so this is not a historical-location dataset. State does not mean the place of incorporation, investor residence or use of proceeds.

Industry pages use the classification on each Form D record. Directory counts include only records with a nonblank issuer name and a recognized directory category. The underlying detail pages may expose additional records. Directory summaries and sitemap XML are cached for 15 minutes each; discovery of a newly populated directory through the sitemap can take roughly 30 minutes when those caches overlap.

## Amounts and missing data

We display extracted offering amounts separately from reported amounts sold. We do not sum amendments into a capital-raised total. An issuer's latest snapshot describes one filing, not all offerings combined. See the [worked amount example](/learn/form-d-offering-amount-vs-amount-sold/).

A dash means a numeric value is unavailable in our database. It can reflect an indefinite or absent source value, or an extraction limitation; do not infer which without opening the source. A reported zero remains zero. Extracted dollar values use whole-dollar storage, so the original document controls when exact precision or explanatory notes matter.

## Reproduce and check a finding

Record the accession number, CIK, filing date, form type, source link and date reviewed. Read amendments and explanatory text before comparing amounts. Our [issuer-history workflow](/learn/research-company-form-d-history/) explains how to keep a research log.

If you find a mismatch, send the accession number, affected field and SEC source link to [our data contact](mailto:luke@dawncrestconsulting.com). Please do not send confidential investor details. We cannot infer valuation, returns, financial performance or current investment availability from the presence of a filing.

Browse [states](/states/), [industries](/industries/), or [recent filings](/recent/) to explore the available records. The original [SEC Form D and instructions](https://www.sec.gov/files/formd.pdf) remain the source for field definitions.
""",
    },
]
