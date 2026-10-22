# Research quality and organic growth backlog

Baseline: 2026-10-22; deployed main `be44756`. Scores are prioritization judgments (1–5), not measured SEO scores. Impact/confidence/value: higher is better; effort/risk: higher is harder.

| Rank | Opportunity and evidence | Impact | Confidence | Effort | Risk | Business value | Decision |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | Correct financial summaries: hubs label sums of offering amounts “Total raised”; issuer sums repeat amended disclosures | 5 | 5 | 2 | 2 | 5 | Implement count-based summaries and explicit limitations |
| 2 | Reduce database work: hub summary uses three aggregate queries; issuer repeatedly fetches first filing; detail relationships load raw XML | 4 | 5 | 2 | 2 | 4 | Measure, consolidate, defer unused data |
| 3 | Add browsable industry/state directories: home links exist but no reusable directory roots | 4 | 4 | 2 | 2 | 4 | Add two data-backed directories; no combinatorial URLs |
| 4 | Improve explanations at point of use: ambiguous amounts, missing zero values, no methodology | 5 | 5 | 2 | 1 | 5 | Add contextual methodology and original-source links |
| 5 | Publish three practical guides: methodology, amount interpretation, issuer-history workflow | 4 | 4 | 3 | 2 | 5 | Source from SEC and actual implementation; cross-link |
| 6 | Give guides a useful landing page: existing /learn is mostly About/pricing content before articles | 4 | 5 | 2 | 1 | 4 | Put research guides first, preserve ads and business links |
| 7 | Report search metrics separately from bots: Cloudflare crawler volume dominates; GSC still processing | 5 | 5 | 2 | 1 | 5 | Repeatable reporting template; no invented baseline |
| 8 | Expand ADV/CF/Reg A sitemap coverage only after completeness and entity checks | 4 | 3 | 4 | 3 | 4 | Defer mass inclusion; audit representative templates |
| 9 | Add monthly original research after coverage and amendment linkage validated | 4 | 3 | 4 | 3 | 5 | Define quality gate; don't publish capital-raised totals |
| 10 | Improve mobile CWV based on field/lab evidence, fonts and third-party resources | 3 | 3 | 3 | 2 | 4 | Measure; avoid claiming field results from local timings |

No production credentials, payment behavior, ad settings, ingestion schema, or indexability expansion for filter combinations are required. New material ships through the existing `seed_articles` predeploy command; publication timestamps remain stable on repeat runs. Deployment-ready PR is the release artifact for this phase.

Additional evidence during final QA: the live ADV result `/adv/801-78074/` returned 404 because the bulk importer can store SEC file numbers while the view accepted only digits. Treated as an immediate reliability fix (impact 5, confidence 5, effort 2, risk 2, value 5). Legacy records now open with noindex, explicit identifier limitations and correct IAPD lookup behavior; regression tests also exposed and fixed the no-match query-slicing error.
