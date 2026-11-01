"""Corrections to the existing ten guide URLs, checked against primary sources.

These are educational workflows, not legal advice or reviewed market conclusions.
No person or professional credential is asserted. Keep original publish dates
when reseeding and only change updated_at when actual content changes.
"""
ARTICLES = [
    {
        "slug": "what-is-form-d",
        "title": "What is SEC Form D? A plain-English guide",
        "meta_description": "Use Form D to identify an issuer and its dated offering disclosures. Learn why a notice is not registration, SEC approval or proof of cash received.",
        "body": """Form D is a notice of an exempt securities offering, rather than a registration statement. [The SEC's filing guidance](https://www.sec.gov/resources-small-businesses/exempt-offerings/filing-form-d-notice) explains the notice requirement and the usual deadline of 15 days after the first sale. For that deadline, a first sale means the first investor's irrevocable contractual commitment, not necessarily cash settlement.

## A research question this notice can answer

Ask: *Which legal entity reported which offering fields on which date?* Start with the CIK and accession number, then record the filing date, submission type and named field. Keep offering amount and amount sold in different columns. Neither field alone establishes valuation, performance or a completed financing.

Use [Form D search](/search/) to find the issuer, then open its history. Multiple notices may concern different offerings. An amendment can update a previous disclosure, so a row count is not a count of funding rounds.

## A useful first research log

| Record | Save this | Check before interpreting |
|---|---|---|
| Issuer | Legal name and CIK | Whether it is your intended entity |
| Submission | Accession, date, D or D/A | Whether an amendment or separate offering is involved |
| Financial fields | Offered and sold, separately | Missing, indefinite, corrected or committed amounts |
| Evidence | Original SEC link and review date | Explanatory text and later disclosures |

[The official form](https://www.sec.gov/files/formd.pdf) is the field reference. In this tool, a dash means no usable stored number; reported zero remains zero. Do not replace the dash with zero in an export analysis.

## Next step

Try the [field-by-field example](/learn/how-to-read-a-form-d/) and [issuer-history workflow](/learn/research-company-form-d-history/). Use [dataset coverage](/research/coverage/) before assuming the available history is complete. This is research guidance, not a legal determination that an issuer complied with an exemption.
""",
    },
    {
        "slug": "reg-d-506b-vs-506c",
        "title": "Rule 506(b) vs. 506(c): which Reg D exemption is being used?",
        "meta_description": "Compare the solicitation and purchaser conditions of Rule 506(b) and 506(c), verify exemption codes and avoid inferring investor identities from Form D.",
        "body": """The exemption code helps identify the rule an issuer says it relies on. It does not certify compliance or identify the purchasers. Check Item 6 of the source filing, including every claimed exemption or exclusion.

## Read the two rules separately

| Question | Rule 506(b) | Rule 506(c) |
|---|---|---|
| General solicitation | Not permitted | Permitted subject to the rule's conditions |
| Purchasers | Unlimited accredited investors; limited non-accredited purchasers with sophistication requirements | All purchasers must be accredited |
| Accreditation | Reasonable belief under the applicable definition; not a blanket permission to rely on any checkbox | Reasonable steps to verify accredited status are required |

[SEC Rule 506(b) guidance](https://www.sec.gov/resources-small-businesses/exempt-offerings/private-placements-rule-506b) specifies no more than 35 non-accredited investors in a 90-calendar-day period and additional disclosure requirements when non-accredited investors participate. [SEC Rule 506(c) guidance](https://www.sec.gov/resources-small-businesses/exempt-offerings/general-solicitation-rule-506c) explains purchaser verification and other conditions. Consult the linked rules for a legal analysis.

## A repeatable verification workflow

1. Open a [Form D record](/search/) and follow its SEC source.
2. Locate the exemption codes: `06b` and `06c` identify the corresponding rules. Other selections can refer to different exemptions or exclusions.
3. Record the exact selection and the filing date. Check later amendments before treating it as current.
4. Keep the total investor count separate from accreditation. The count is not a list of purchasers or proof of each purchaser's status.

Do not infer how a sale was marketed from the issuer's name, industry or website. A `06c` selection does not prove a public campaign occurred; a `06b` selection does not establish that every purchaser is accredited. [Compare dated disclosures](/research/filing-changes/) and preserve source links when a research question depends on a change.
""",
    },
    {
        "slug": "form-d-vs-form-d-a",
        "title": "Form D vs. Form D/A: what amendments actually mean",
        "meta_description": "Compare original notices and amendments without inventing offering chains. Learn why differences between disclosures are not automatically new capital or investors.",
        "body": """D/A is an amended Form D notice. A shared issuer CIK helps locate records, but does not establish which offering an amendment updates. An issuer may have several offerings in progress.

[The SEC Form D instructions](https://www.sec.gov/files/formd.pdf) describe amendments for material errors, certain changes and annual updates for continuing offerings, with exceptions. A researcher should read the amended notice's explanations rather than assume each new filing means another financing.

## Use the change viewer carefully

Open an issuer from [search](/search/) and choose **Compare filings**. The [change viewer](/research/filing-changes/) displays two dated disclosures and arithmetic differences in their stored numeric fields. Those are differences between records; the tool does not claim an offering-level match.

| Situation | What the tool does | Research implication |
|---|---|---|
| Both amounts are usable | Shows later minus earlier | Verify common offering and correction context |
| Either amount is missing | Shows no difference | Missing is not zero |
| Both filings have the same date | Suppresses directional differences | Stored dates do not establish sequence |
| Investor count decreases | Preserves a negative difference | It is not proof of investor withdrawals |

## Worked example, hypothetical

An initial notice reports $2 million sold; a later amendment for the same offering reports $3 million. Their sum, $5 million, duplicates earlier sales. The $1 million arithmetic difference still requires checking for corrections and noncash commitments before describing proceeds received in the interval.

Record both accession numbers in your notes. If offering identity remains uncertain, describe the disclosures separately. No amendment is evidence of SEC approval, and a lack of amendments does not establish that an offering closed. See the [amount guide](/learn/form-d-offering-amount-vs-amount-sold/) for the full example and the [coverage page](/research/coverage/) for import limitations.
""",
    },
    {
        "slug": "what-is-form-c",
        "title": "What is Form C? A guide to Reg CF crowdfunding filings",
        "meta_description": "Research a Regulation Crowdfunding issuer using Form C disclosures, amendments and ongoing reports. Separate the target, offered securities and reported progress.",
        "body": """Form C is a disclosure used for Regulation Crowdfunding offerings. [The SEC's overview](https://www.sec.gov/resources-small-businesses/exempt-offerings/regulation-crowdfunding) describes an aggregate offering limit of $5 million in twelve months and transactions through an SEC-registered broker-dealer or funding portal. Non-accredited investors have investment limits; retail eligibility does not mean an unrestricted investment.

## Read the offering, then the updates

Use [Form C search](/cf/) to find the legal issuer, target and intermediary. Open the source document, including attachments. An extracted target is not the amount ultimately sold, and the presence of an initial disclosure does not establish a successful campaign.

Build a log of the original C, amendments and subsequent reports visible in EDGAR. A C/A changes a disclosure; C-U reports progress; C-AR is an annual report, and C-TR relates to termination of reporting. These submission types have different purposes and should not be counted as independent campaigns.

## Three questions before comparing issuers

1. Are you comparing the same financial concept: target, maximum offering, or reported progress?
2. Do the dates and reporting periods align?
3. Are the documents complete, including risk factors, intermediary details and the applicable financial statements?

Do not assume every Form C has audited financial statements or that a portal's presence validates the issuer. Financial-statement requirements depend on offering size and other conditions; consult current SEC guidance and the actual attachments rather than extrapolating a threshold table.

A [Form D comparison](/learn/form-d-vs-form-c/) can add another disclosure trail when the same CIK appears in both datasets. It cannot establish that the records represent one combined raise. Preserve original accessions and dates, and verify missing records directly with EDGAR. This guide is a research workflow, not a recommendation to invest or a determination of offering eligibility.
""",
    },
    {
        "slug": "form-d-vs-form-c",
        "title": "Form D vs. Form C: how to research the disclosures together",
        "meta_description": "Compare a Form D notice with Form C crowdfunding disclosures by legal issuer, field definition, reporting date and source, without adding overlapping amounts.",
        "body": """Form D and Form C serve different disclosure purposes. A Form D notice reports an exempt offering; a Form C supplies disclosures for a Regulation Crowdfunding offering. Neither is evidence, by itself, that a financing closed.

## Compare evidence rather than labels

| Research question | Form D trail | Form C trail |
|---|---|---|
| Which issuer? | Legal issuer and CIK | Legal issuer and CIK |
| Which amount? | Offered and reported sold are separate | Target, maximum and progress are separate |
| Which time? | Notice date and amendments | Offering disclosure, amendments and later reports |
| What to verify? | Exemption and explanatory fields | Intermediary, attachments and progress reports |

Use the [SEC Form D filing guidance](https://www.sec.gov/resources-small-businesses/exempt-offerings/filing-form-d-notice) and [Regulation Crowdfunding overview](https://www.sec.gov/resources-small-businesses/exempt-offerings/regulation-crowdfunding) as the definitions for each trail. The crowdfunding intermediary can be a registered broker-dealer or a funding portal; it is not limited to one platform type.

## An issuer-level research workflow

1. Find the company in [Form D search](/search/) and [Form C search](/cf/).
2. Match CIKs, not just brand names. Different legal vehicles may use similar names.
3. Read each source and preserve its accessions, dates and field labels.
4. Compare terms and reporting periods before making a combined observation.
5. Keep amounts separate unless independent evidence establishes a nonoverlapping scope.

A company can use different exemptions at different times. The presence of both forms does not establish a particular financing sequence, a change in investor strategy or a sum of capital received. A missing cross-link may reflect incomplete stored coverage. Use the [issuer-history workflow](/learn/research-company-form-d-history/) to keep a source log, and describe uncertain relationships explicitly.
""",
    },
    {
        "slug": "what-is-form-1a",
        "title": "What is Form 1-A? A guide to Regulation A offerings",
        "meta_description": "Read a Form 1-A offering statement, distinguish amendments from SEC qualification, and inspect later Regulation A reports without inferring an offering outcome.",
        "body": """Form 1-A is an offering statement under Regulation A. [The SEC's Regulation A overview](https://www.sec.gov/resources-small-businesses/exempt-offerings/regulation) describes two tiers: up to $20 million for Tier 1 and $75 million for Tier 2 over twelve months. Tier 2 adds audited financial statements, ongoing reports and certain non-accredited investor limits. Regulation A is an exemption from registration.

## Filing is not qualification or completion

Start in [Regulation A search](/1a/), then open the SEC document. A submitted 1-A is not, by itself, a qualified offering. Amendments revise the statement. A qualification notice has a different purpose, and a withdrawal has another. Keep these distinct in a timeline.

A historical qualification does not establish that an offering is currently available, that it reached its maximum, or that the SEC endorsed its merits. Read the latest relevant documents and status notices in EDGAR.

## A practical review checklist

| Save from the source | Why it matters |
|---|---|
| Legal issuer, CIK and accession | Establishes the entity and document |
| Tier and filing date | Sets the disclosure context |
| Offered securities and terms | Prevents comparing unlike instruments |
| Risk factors and financial statements | Supplies context an extracted amount cannot |
| Later amendments and reports | Identifies changes after the initial statement |

Do not apply Tier 2 financial requirements to all Tier 1 offerings. Avoid estimating legal cost, processing time, returns or current funding progress from the form type alone. These require additional evidence.

[Compare Form D and Form 1-A](/learn/form-d-vs-form-1a/) when the same issuer has both trails, keeping offering amounts and issuer-reported sales separate. Paid exports organize stored fields; they do not substitute for reading the full offering circular and its later updates. This is research information, not legal or investment advice.
""",
    },
    {
        "slug": "form-d-vs-form-1a",
        "title": "Form D vs. Form 1-A: notices and offering statements",
        "meta_description": "Distinguish a Form D exempt-offering notice from a Regulation A Form 1-A offering statement. Compare issuer identity, dates and disclosure status accurately.",
        "body": """A Form D is an exempt-offering notice. A Form 1-A is a Regulation A offering statement. Calling both forms registration documents obscures their different roles.

## Build two timelines

Use [Form D search](/search/) and [Regulation A search](/1a/) to locate the legal issuer. Preserve the CIK, accession, submission type and filing date for every relevant document. Then read the [SEC's Form D guidance](https://www.sec.gov/resources-small-businesses/exempt-offerings/filing-form-d-notice) and [Regulation A overview](https://www.sec.gov/resources-small-businesses/exempt-offerings/regulation) to interpret each trail.

| Comparison | Form D | Form 1-A |
|---|---|---|
| Role | Notice of an exempt offering | Regulation A offering statement |
| Updates | Amended notices | Amendments and separate status/report documents |
| Amount caution | Offered and reported sold are distinct | Offered maximum is not a result |
| Status caution | Not SEC approval | Submission alone is not qualification |

## What cross-filing research adds

When the CIK matches, you can organize different disclosures for the same filer. That is useful for identifying which documents to read next. It does not prove the offerings are the same, establish which transaction funded a business, or show that an issuer moved from one strategy to another.

In a hypothetical case, a $10 million Form D offering and a $20 million Form 1-A offering do not establish $30 million raised. They may differ in timing, offered securities and reported progress. The amounts should remain separate until sources establish their relationship.

Do not infer qualification, current availability or investment quality from a database category. Follow status notices, amendments and later reports in the SEC source. For detailed reading, use the [Form 1-A guide](/learn/what-is-form-1a/) and [Form D amount guide](/learn/form-d-offering-amount-vs-amount-sold/).
""",
    },
    {
        "slug": "what-is-form-adv",
        "title": "What is Form ADV? The investment adviser disclosure form",
        "meta_description": "Use Form ADV and IAPD to examine an adviser's business, fees, disclosures and identity. Understand why reported assets and registration do not establish performance.",
        "body": """Form ADV describes an investment adviser. [The SEC's Investor.gov explanation](https://www.investor.gov/introduction-investing/investing-basics/glossary/form-adv) distinguishes structured business information, narrative brochures and the relationship summary applicable to certain retail relationships. It is different from a Form D offering notice.

Part 1 supplies structured information about the firm. Part 2 provides narrative disclosures about practices, fees and conflicts. An appropriate review reads the relevant parts together, rather than relying on a single extracted assets figure.

## A practical adviser review

1. Search [advisers](/adv/) by legal name or identifier.
2. Open the linked [IAPD record](https://adviserinfo.sec.gov/) and confirm the CRD/SEC identifiers and filing date.
3. Read the brochure's fee and conflict sections, alongside relevant disclosures.
4. Record whether a field is firm-wide or relates to a particular account or vehicle.
5. Reconcile different reporting dates before comparing records.

A similarly named fund and adviser may be distinct entities. A suggested match on an issuer profile is a research lead, not a verified ownership or management relationship.

## Three interpretation traps

- **Assets are not investment returns.** Reported regulatory assets under management are not a performance history or proof of fundraising in a period.
- **Headcount is not strategy.** A ratio of assets to employees does not establish whether a manager is systematic, active or effective.
- **Registration status is not a quality rating.** Check the current source status and disclosures; do not infer SEC endorsement.

Registration and reporting obligations have exceptions. This guide does not replace the applicable rules with one assets threshold or classify an exempt reporting adviser as a registered adviser. Use the current IAPD record for the specific entity and seek qualified advice when a legal classification matters. The [cross-filing workflow](/learn/form-d-vs-form-adv/) explains how to preserve the distinctions while researching a possible adviser relationship.
""",
    },
    {
        "slug": "form-d-vs-form-adv",
        "title": "Form D vs. Form ADV: how to read them together",
        "meta_description": "Research a possible issuer-adviser relationship using CIKs, CRDs and original disclosures. Keep offering amounts, adviser assets and unverified name matches distinct.",
        "body": """Form D organizes an offering disclosure; Form ADV organizes adviser information. Reading both can guide research into a possible relationship, but a name match cannot establish that relationship.

## Keep the identifiers separate

| Research object | Identifier | Source question |
|---|---|---|
| Form D issuer | CIK and filing accession | Which legal issuer reported this offering? |
| Investment adviser | CRD/SEC identifier and dated filing | Which firm reported these business details? |
| Possible relationship | Explicit supporting source | Does a document actually connect these entities? |

Read the [SEC Form D guidance](https://www.sec.gov/resources-small-businesses/exempt-offerings/filing-form-d-notice) and [SEC adviser disclosure explanation](https://www.investor.gov/introduction-investing/investing-basics/glossary/form-adv) for the different purposes of these forms. The adviser may be a separate entity from a fund issuer, and neither a shared word nor a shared address is sufficient evidence of control.

## A reproducible connection check

Find the issuer in [Form D search](/search/), then inspect any suggested adviser in [adviser search](/adv/). Open both original sources. Look for explicit references in the relevant disclosures or attachments and record the exact legal entities and dates. If no confirming evidence is available, label the match unverified.

## Avoid false financial comparisons

In a hypothetical example, a notice reports a $100 million offering and $42 million sold; an adviser reports $1.2 billion of regulatory assets on a different date. These figures do not establish a fund's cash receipts, the adviser's performance, an eight-year track record or that the adviser manages this issuer. Offering disclosures and adviser assets measure different things.

Use the [issuer-history workflow](/learn/research-company-form-d-history/) to preserve source links and record unresolved questions. Do not call an offering a side pocket, flag a discrepancy as misconduct or infer manager quality from these numbers alone.
""",
    },
    {
        "slug": "how-to-read-a-form-d",
        "title": "How to read a Form D: a field-by-field walkthrough",
        "meta_description": "Use an annotated SEC example and field checklist to read issuer identity, exemptions, offered amounts, reported sales and investor counts accurately.",
        "body": """Start with the document identifier, not the headline amount. An accession identifies a submission; a CIK identifies a filer. Keep the submission date with every observation.

## A real SEC example, with a verification trail

BigHat Biosciences, Inc. submitted Form D accession **0001231919-26-001499** on **October 26, 2026**, under CIK **1797256**. The [SEC filing index](https://www.sec.gov/Archives/edgar/data/1797256/000123191926001499/0001231919-26-001499-index.htm) identifies the submission and links its primary document. This is an example of reading a disclosure, not an endorsement or a conclusion about a financing outcome.

Read the [original primary document](https://www.sec.gov/Archives/edgar/data/1797256/000123191926001499/primary_doc.xml) alongside the [issuer search](/search/?q=BigHat). The SEC source was checked November 1, 2026. Item 13 reports **$79,999,947 offered** and **$75,141,086 sold**, while Item 14 reports **29 investors**. Subtracting sold from offered gives **$4,858,861**, matching the reported remaining amount. This arithmetic checks the fields; it does not prove cash receipt, current availability or a financing completion. Item 6 selects Rule 506(b).

## Annotate the fields

| Source field | Record in your note | Avoid this inference |
|---|---|---|
| Issuer identity | Name and CIK | Similar name means the same legal entity |
| Submission type | D or D/A and accession | Every record is another round |
| Industry | Issuer's selected classification | Independently verified business model |
| Exemption selections | Exact codes | Verified compliance or purchaser identity |
| Offering amount | Named field, date and value | Cash already received |
| Amount sold | Separate named field and date | Independently confirmed cash settlement |
| Investor count | Reported count, including zero | List of named purchasers |

[The SEC Form D and instructions](https://www.sec.gov/files/formd.pdf) supply the field definitions. Related persons are disclosed roles, not a purchaser list. A minimum investment is a reported term; it does not establish what every investor contributed.

## Finish with a history check

Open the issuer profile, then use [filing comparisons](/research/filing-changes/) for two available dates. Confirm offering identity in the documents before interpreting a difference as a change to one offering. Keep missing values blank and source links with your notes. Read the [amount interpretation example](/learn/form-d-offering-amount-vs-amount-sold/) before adding any figures.
""",
    },
]
