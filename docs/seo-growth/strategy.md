# Organic research strategy — 22 October 2026

## Evidence and positioning

This is a prioritized research plan, not a forecast of rankings or traffic. No paid keyword-volume dataset was available. Search-result and competitor inspection establish that these intents have competing destinations; they do not establish monthly volume, conversion rate, or attainable rank. Competition below is a qualitative assessment of the destinations observed and the specificity of the query.

Primary competitor observations:

- [FormDs.com](https://www.formds.com/) organizes company/fund/person lookup and location discovery. Competing on another generic filing list is weak differentiation; our opportunity is a transparent issuer workflow across filing types and careful amendment interpretation.
- [Fundz's Form D API](https://app.fundz.net/form-d-api) and [fund-formation API documentation](https://app.fundz.net/knowledge/api-references/fund-formations) emphasize structured records, filters and commercial research. Our opportunity is accessible source-linked research with clear limitations. Their marketing claims are not evidence of our demand or performance.
- [Advisor Growth Database](https://www.advisorgrowthdatabase.com/) targets adviser research. We should first resolve adviser identifiers and coverage, then offer focused research pages rather than index incomplete search results.
- SEC EDGAR and IAPD are the authoritative verification destinations. Form D Explorer should reduce the effort of finding and comparing disclosures while preserving direct source access, not imply that it replaces source review.

The durable advantage is the connected workflow: source record → identified issuer → available history → meaningful category → explanatory guide → saved research/export. Accuracy and reliable coverage must precede more landing pages. Google's [people-first guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content) and [scaled-content policy](https://developers.google.com/search/docs/essentials/spam-policies) support this direction; neither predicts rankings.

## Prioritized keyword-to-page map

Evidence: **Observed** means a related result/competitor intent was inspected; **Source-backed** means primary SEC material and the existing dataset support a useful answer; **Hypothesis** means demand still needs GSC evidence. All volumes are **unavailable**. Competition and conversion potential are judgments, not measured outcomes. One canonical destination per intent; variants belong on the same page.

| Priority | Cluster / representative variants | Audience and intent | Destination | Evidence / competition | Business relevance / conversion path |
|---|---|---|---|---|---|
| 1 | SEC Form D filings; Form D lookup; private placement database | Researchers finding records | `/` then `/search/` (search stays noindex) | Observed / high | High; search → issuer → export |
| 2 | [legal issuer name] Form D; [company] SEC offering history | Entity-specific diligence | `/issuer/<slug-cik>/` | Observed / varies by entity | High; history → follow issuer |
| 3 | [issuer] Form D [filing date/accession] | Verify an exact disclosure | `/filing/<accession>/` | Source-backed / narrower | High; source → related records |
| 4 | Form D offering amount vs amount sold; amendment double counting | Analysts interpreting numbers | New amount guide | Source-backed / moderate | High; guide → filing research |
| 5 | How to find company Form D history; private offering history | Researchers learning workflow | New issuer-history guide | Observed + source-backed / moderate | High; guide → search/account |
| 6 | California Form D filings; Texas private placements; New York Form D | Geographic discovery | Existing `/state/<code>/`; `/states/` directory | Observed / moderate to high | High; browse → issuer/export |
| 7 | Biotechnology private placements; real estate Form D filings | Industry research | Existing `/industry/<slug>/`; `/industries/` directory | Observed / moderate | High; compare records → export |
| 8 | Recent Form D filings; recently disclosed private offerings | Recurring discovery | `/recent/` | Observed / high | High; repeat research/saved search |
| 9 | How to read Form D; what does Form D reveal | Learning interpretation | Existing `/learn/how-to-read-a-form-d/` | Source-backed / high | Medium-high; worked example → tool |
| 10 | Form D vs D/A; Form D amendment meaning | Interpret submissions | Existing `/learn/form-d-vs-form-d-a/` | Source-backed / moderate | Medium-high; related filing review |
| 11 | Form ADV lookup; investment adviser research | Adviser diligence | Existing ADV guide → `/adv/`; future quality-controlled ADV landing page | Observed / high | High; identifiers and source verification first |
| 12 | [adviser name] CRD / Form ADV | Entity lookup | `/adv/<numeric-crd>/` | Observed / entity dependent | High; cross-product research; no claim name match proves identity |
| 13 | Form C filings; crowdfunding disclosure lookup | Researchers examining crowdfunding | Existing Form C guide → `/cf/`; qualified detail pages | Source-backed / high | Medium-high; source review/export |
| 14 | Regulation A offering disclosures; Form 1-A lookup | Analysts comparing offering disclosures | Existing Form 1-A guide → `/1a/` | Source-backed / high | Medium-high; verify identity and filing type |
| 15 | 506(b) vs 506(c); Regulation D exemptions | Founders, attorneys, researchers | Existing comparison guide | Source-backed / high | Medium; educational entry; legal review needed for updates |
| 16 | Form D dataset coverage; SEC filing data limitations | Evaluating data providers | New methodology guide | Source-backed / narrow | High trust value; qualified export use |
| 17 | Monthly Form D filing counts by industry/state | Research and reporting | Future single monthly research series | Hypothesis / unknown | Potentially high; requires coverage gate, not fundraising sums |
| 18 | Private fund Form D research; fund manager disclosure history | Fund researchers | Improve existing issuer/history workflow first | Observed / high | High; no new keyword-only fund directories yet |

## Existing content audit

The ten seeded articles cover Form D, 506(b)/506(c), D versus D/A, Form C, D versus C, Form 1-A, D versus 1-A, ADV, D versus ADV, and reading Form D. Preserve their established slugs. The “what is Form D” article had statements that could imply financial-performance visibility and infer valuation; those statements are corrected in this change. Comparison articles have distinct intents, but their lead explanations should stay concise and link to the canonical form guide rather than repeat full definitions.

The largest gaps were methodology, amount interpretation and a reproducible company-history workflow. Three new guides address them, link to primary SEC sources, and are linked back from tools. `/learn/` now presents guides before About/pricing material. The existing guide library has not received an exhaustive securities-law review; requirement/timing statements need periodic primary-source review before expansion.

## Editorial calendar: 20 opportunities

Weeks are relative to release and available review capacity, not scheduled publications. Keep each existing URL when refreshing its intent. A proposed item is publishable only after source review and any data gate below.

| Order / timing | Opportunity and destination | Original value / primary source | Acceptance condition and measurement |
|---|---|---|---|
| 1 / release | Offering amount vs amount sold (new; implemented) | Worked hypothetical amendment example; [Form D instructions](https://www.sec.gov/files/formd.pdf) | Separate fields, no summed proceeds; guide → filing clicks |
| 2 / release | Company Form D history workflow (new; implemented) | CIK and accession research log; [CIK lookup](https://www.sec.gov/search-filings/cik-lookup) | Explain entity uncertainty; guide → search usage |
| 3 / release | Coverage/methodology (new; implemented) | Actual importer, stored fields and cache behavior; [EDGAR access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) | Limits match implementation; support accuracy questions |
| 4 / weeks 1–2 | Refresh “what is Form D” (partly implemented) | Correct unsupported financial claims; Form D instructions | Review remaining timing/exemption claims; GSC query fit |
| 5 / weeks 2–3 | Improve “how to read Form D” | Annotated real filing with source/date and missing fields | Verify every example against SEC; record engagement |
| 6 / weeks 2–3 | Refresh D vs D/A | Original/amended side-by-side source example | Verified same offering; no automatic economic-event inference |
| 7 / weeks 3–4 | Missing, indefinite and zero amounts | Field-level examples, parser behavior | Verify distinct source states; link from amount guide |
| 8 / weeks 3–4 | Find recent disclosures without assuming a closing date | Repeatable `/recent/` + search workflow | Source/date vs transaction distinction; return usage |
| 9 / weeks 4–5 | Research an adviser using CRD and SEC file number | IAPD workflow; [SEC ADV FAQ](https://www.sec.gov/about/divisions-offices/division-investment-management/electronic-filing-investment-advisers-iard/frequently-asked-questions-form-adv-iard) | Correct CRD mapping and actual screenshots before publication |
| 10 / weeks 4–5 | Refresh existing ADV explainer | Separate regulatory AUM from performance and firm identity | Primary-source review; adviser-tool engagement |
| 11 / weeks 5–6 | Entity names, CIKs, funds and managers | Real ambiguous-name example using SEC records | No unverified relationships; source-linked identity checklist |
| 12 / weeks 5–6 | Export research without duplicate accessions | Reproducible spreadsheet workflow, no invented return metrics | Test current export fields and gates; qualified export conversions |
| 13 / weeks 6–7 | Improve California research hub | Explain stored-address geography with actual filing counts | Coverage reviewed; existing URL only; nonbrand impressions |
| 14 / weeks 6–7 | Improve biotechnology research hub | Useful filing examples and classification limits | Actual supported industry values; no fundraising league table |
| 15 / weeks 7–8 | Refresh Form C explainer with a worked disclosure | SEC Form C and original filed document | Distinguish target/maximum/financial statements; source audit |
| 16 / weeks 7–8 | Refresh Form 1-A guide | Filing vs qualification vs termination context using SEC sources | Legal/subject-matter review; resolved issuer names |
| 17 / weeks 8–9 | Refresh 506(b)/506(c) comparison | SEC rule guidance, links to actual exemption fields | Current requirements verified; not personalized legal advice |
| 18 / weeks 9–10 | First monthly disclosure-activity report | Reproducible count queries and available coverage | Ingestion completeness, amendment classification and denominators validated; cite query/version |
| 19 / weeks 10–11 | Industry disclosure activity comparison | Counts, distinct CIKs, original/amended mix | Stable coverage; explain selection bias; no capital-raised total |
| 20 / weeks 11–12 | Geography and address changes in filing data | Source-backed example of issuer movement | Historical address provenance available or explicitly limit to stored location |

## Quality gate for future pages

Require a verified identifier, meaningful original record fields, a resolvable source, distinct research intent, canonical URL, and useful inbound/outbound internal links. A numeric identifier's format alone is not verification. Sample records against sources before broad sitemap inclusion. Do not create city × industry × year × exemption combinations from search filters. Empty collections remain noindex/404; boilerplate-only or unresolved-identity records need a repair queue and explicit eligibility rule. Do not bulk remove existing indexed records without an inventory and impact review.

New filings flow into existing templates and bounded sitemap sections automatically. Counts update from the database; cached directory summaries expire after 15 minutes. Article timestamps change only when content changes. Monthly research requires a separately reproducible coverage snapshot and should not infer the total private-market economy from this dataset.
