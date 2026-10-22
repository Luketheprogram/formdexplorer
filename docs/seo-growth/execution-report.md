# SEO and research-quality execution report

Date: 22 October 2026. Baseline: production/main `be447563de519bc2c9c1e62fa36d23d0392bd0aa`. Release branch: `codex/research-quality-growth`. This report describes a tested, deployment-ready change, not a production release or achieved traffic growth.

## A. Executive summary

The existing SEO foundation was already substantial: Django server-rendered HTML, centralized metadata/canonical policy, split cached sitemaps, noindex rules for utility/filter pages, and accurate article publication timestamps. Those systems were preserved.

The main improvement is research credibility. State/industry pages previously labeled summed offering amounts “Total raised”; issuer pages summed original and amended disclosures and used dollar-sized bars under “Filings by year.” These can mislead users. They now show submission counts, distinct issuers, original/amendment counts, available dates, and a clearly labeled latest-filing snapshot. Offering amounts and reported amounts sold remain separate; zero values are retained. Source and methodology links are visible at the point of use.

Two directory roots, three practical guides, contextual links and clearer guide navigation provide useful paths into the dataset. Query consolidation and deferring unused XML reduce database work. The importer now honors SEC D/A index classifications even when the XML omits submission type.

A final representative live check also found a genuine broken journey: ADV search links to legacy SEC file-number identifiers, while the detail view accepted only numeric CRDs. These profiles now open with accurate identifier labels, a verification explanation, a general IAPD lookup link, and noindex until identity is resolved. Numeric CRD behavior remains intact. New regression tests also exposed an existing no-match adviser error caused by filtering an already sliced query; the helper now applies its existing limit after filtering. No identifier migration or data merge was attempted.

The most valuable next opportunity is **record quality and coverage reconciliation**, especially historical D/A classifications, placeholder Reg A issuer names, and adviser CRD mapping. More URLs should follow demonstrable source quality, not precede it.

## B. Evidence-based SEO scorecard

| Category | Before | After in this branch |
|---|---|---|
| Crawlability | Public content present in raw response HTML; canonical origin and pagination already implemented. A real ADV search-result link returned 404. | Preserved server rendering; new crawlable directory/context links; legacy adviser record links repaired. |
| Indexability | Search, private, pagination and empty content policies existed. Some non-D detail quality remained weak. | Empty new directory roots noindex and absent from sitemap; unresolved legacy adviser identifiers noindex. Existing filter/private protections retained. |
| Metadata | Central `config/metadata.py` and context processor already produce unique titles/descriptions, canonical and social metadata. | New roots/guides use the same system; state visible headings use full names; adviser titles distinguish identifier types. |
| Sitemap | Canonical sections, 5,000 URLs per file, cached 15 minutes; filing/issuer `lastmod` omitted rather than fabricated; article update dates available. | Populated directory roots and published guides integrate with existing sections. No bulk ADV/CF/Reg A expansion. |
| Structured data | Organization, WebSite, WebPage, BreadcrumbList and Article graph already present. | New directory/hub breadcrumb hierarchy matches visible navigation. JSON parses and canonical graph links tested. No rich-result guarantee. |
| Internal linking | Home/category/issuer/filing links existed, but no directory root and limited methodology/tool connections. | State/industry directories, corrected breadcrumbs, guide-to-tool and tool-to-guide links, contextual SEC links and research footer. |
| Performance | Local warm queries: home 3, state 8, industry 6, issuer 16, filing 3. | 1, 6, 4, 12, 3 respectively; XML removed from detail queries. Not all timings improved; see F. |
| Content usefulness | Ten seeded guides; `/learn/` primarily led with About content; misleading summary amounts. | Three sourced workflow guides; existing Form D explanation corrected; guides first; financial limitations visible. |
| Programmatic SEO | Useful records/categories already existed; indiscriminate monetary totals overstated meaning. | Count-based reusable templates, cached data-backed directory roots, source/context links and explicit coverage limits. No keyword-combination page factory. |

### Route and intent inventory

All HTML families use the shared metadata/schema layer. `public-baseline.json` records raw HTTP observations, including the failed adviser URL; its timings are single request durations, not TTFB or CWV benchmarks.

| Family | Intent / audience / unique value | Index and crawl policy | Linking, conversion, performance |
|---|---|---|---|
| `/` | Form D lookup; researchers; recent records and categories | Canonical public landing | Links to search, records/categories; latest 20 records, cached directory aggregates |
| `/recent/` | Ongoing discovery; filing date and issuer | Page 1 public; later pages noindex with crawlable links | Issuer/detail navigation; bounded pagination |
| `/states/`, `/industries/` | Compare populated categories; counts/dates | New roots public only if populated | Link to existing unique hubs; 2 grouped queries on cache miss, 0 on hit |
| `/state/<code>/`, `/industry/<slug>/` | Focused geographic/industry research | Populated first page eligible; empty/no-data behavior retained; pagination noindex | Counts, top issuers, filings, guides; 50-row pages; consolidated stats |
| `/issuer/<slug-cik>/` | Entity history and identification | Nonblank named issuer with Form D records eligible; corrected aliases redirect; later pages noindex | Latest snapshot, yearly counts, source detail, follow action; name suggestions explicitly uncertain |
| `/filing/<accession>/` | Exact record/source verification | Named-issuer canonical detail eligible; missing record 404 | Extracted fields, SEC link, issuer/industry/other filings; no raw XML load |
| `/adv/`, `/cf/`, `/1a/`, `/search/` and partials | Interactive research/filtering | Utility/search noindex, follow; excluded from sitemap | Search/export workflows preserved; bounded results; cross-product queries defer raw XML |
| `/adv/<id>/` | Adviser identification and disclosures | Numeric CRD detail retains existing eligibility; legacy SEC-number records now noindex | Correctly labeled identifiers; source verification; approximate entity matches; quality audit needed |
| `/cf/<accession>/`, `/1a/<accession>/` | Exact crowdfunding/Reg A records | Existing detail eligibility retained, no new sitemap section | Unique source fields/source links; placeholder-name example needs repair before expansion |
| `/learn/`, `/learn/<slug>/`, `/learn/api/` | Education, research methodology, API discovery | Published nonempty articles eligible; drafts/future/empty excluded; API help route reserved | Guides first; related guides, research CTAs; Article dates remain stable |
| `/pricing/`, `/privacy/`, `/terms/` | Product and trust information | Public canonical pages retained | Existing pricing and account links preserved |
| Account, auth, saved searches, watchlist, person search, exports, checkout, APIs, feeds, admin | Personal/transactional/utility functions | Existing noindex rules; authentication and payment gates unchanged | No cache of private HTML; no new tracking or monetization behavior |

Parameter combinations remain search utilities, not new landing pages. Unknown paths return real 404s with noindex. Earlier phase checks verified primary host handling, robots and sitemap behavior; this branch does not alter them. Representative routes and policies are tested, not an exhaustive crawl of every production record. Country-like SEC state codes already present in the old sitemap are not silently removed; new roots list recognized US states only.

## C. Code changes and validation

New reusable systems: `filings/research.py` (single-query activity summaries and cached directories), `content/research_guides.py` (three seeded source-linked guides), reusable research note/directory templates, and `scripts/check_public_seo.py` (read-only release checks), and `scripts/benchmark_research.py` (disposable SQLite benchmark harness).

Modified application areas:

- `filings/views.py`, `urls.py`, `sitemaps.py`, `templatetags/seo.py`; issuer, filing, industry/state and stats templates.
- `filings/ingest/pipeline.py`, `xml_parser.py`: SEC index submission type takes precedence; root XML submission type recognized.
- `advisers/models.py`, `views.py`, `matching.py`, detail/results templates: legacy identifier compatibility, accurate labels and source links, noindex for unresolved CRDs. Properties only; no model fields changed.
- `crowdfunding/views.py`, `rega/views.py`: defer unused XML in display queries.
- `content/views.py`, article seeding command, article detail/list and shared base templates: guides, related links and source limitations.
- Tests: new `filings/tests/test_research.py`, `advisers/tests.py`, and parser regressions in `filings/tests/test_xml_parser.py`.
- Evidence/runbooks: this directory, `strategy.md`, `measurement-template.csv`, `backlog.md`, before/after JSON, public baseline, smoke results and preview screenshots.

Validation performed:

- Full Django test suite: **73 tests pass**, including existing SEO/metadata, ads, account/export gating coverage and new count/cache/guide/parser/adviser checks. These are automated checks, not a live purchase test.
- Django system check passes. Tailwind production CSS compiles; collectstatic succeeds. Tailwind emits the existing outdated Browserslist dataset advisory.
- `git diff --check` passes. No new dependencies or migrations.
- Seed command run against an isolated SQLite preview database; tests confirm repeated seeding preserves timestamps when content is unchanged.
- Local HTTP smoke: **75 checks pass**, six sitemap files, 2,124 unique content URLs from synthetic data. Checks cover statuses, canonical URLs, titles/descriptions, single H1, indexing directives, JSON-LD, robots, XML shape, origin, bounds and uniqueness. These counts are not production content counts.
- Desktop and 390px mobile inspection: state page, guide list/article, directory roots, issuer/filing/industry/home layouts; no horizontal page overflow on those mobile routes. Mobile menu and guide link work. Numeric/legacy adviser, CF and Reg A detail routes also render at 390px without horizontal page overflow. Screenshots use synthetic fixtures, not actual company data.
- Live raw-HTML baseline inspected home/recent, state/industry, guides, pricing/login and all four product families. The adviser 404 prompted the repair described above.

Unavailable/not performed: full production PostgreSQL load test, field LCP/INP/CLS, controlled browser Lighthouse runs, Rich Results Test service validation, real payment transaction, and exhaustive per-record crawl. Local schema parsing is not Google's rich-result eligibility decision. Browser automation of every ad-consent state was not repeated; existing server tests cover ad behavior and no ad logic changed. No claim of improved ranking, indexed count or conversion rate follows from these tests.

### Railway release and rollback

1. Review and merge the PR through the established GitHub procedure. This phase stops at a deployment-ready PR.
2. Railway web service builds via existing `nixpacks.toml` (Tailwind + collectstatic). Existing `railway.json` predeploy runs migrations and `seed_articles`; this release adds no migrations. Confirm logs show the three guide slugs created and existing content updated.
3. Verify deployment **SUCCESS** for the merged commit, not merely queued/building. Confirm production canonical/indexing settings from `docs/seo.md` remain correct. Deploy the ingestion service/job from the same commit so the future D/A fix is actually used there.
4. After deployment run `.venv/bin/python scripts/check_public_seo.py --all-sitemaps`; inspect one actual issuer, filing, state, industry, numeric-CRD adviser, legacy-identifier adviser, CF and Reg A record. Verify search/export/auth flows without spending money. Allow cache expiry (15 minutes per layer; nested directory/sitemap caches can delay a newly populated directory root for up to roughly 30 minutes).
5. Keep existing Search Console domain verification and submitted `/sitemap.xml`. The same index discovers new eligible URLs; avoid submitting thousands of individual URLs. Inspect a small representative sample after release.
6. If rollback is needed, redeploy the previous successful commit. No schema reversal is necessary. Seeded article text persists in the database: reseed the old version for prior article bodies; set only the three new articles to draft through admin if their new-directory links must disappear. Back up article values before any such targeted content change. Do not delete filing data. Historical records already imported with corrected types should not be rewritten to an incorrect type on rollback.

## D. Highest-value keywords

See [strategy.md](strategy.md): 18 prioritized intent clusters, one preferred destination each, audience, evidence, competition judgment, business relevance and conversion path. It also contains the required **20-opportunity editorial calendar**. There are no invented volumes or ranking claims. Favor exact entity/filing intent, amount interpretation, company history and populated state/industry research before broad competitive head terms.

## E. Programmatic SEO plan

Built: two directory roots backed by actual recognized categories; improved state/industry/issuer/detail templates; automatic count refresh; context/source links; data explanations and conservative eligibility for unresolved adviser identities.

Preserved: canonical source URLs, query-free sitemap content URLs, bounded pagination and sitemap sections, existing record discovery, noindex search combinations, stable article dates. New filings naturally enter existing query-backed views and sitemaps. We do not invent `lastmod` for records merely because the site was redeployed.

Next: introduce a reusable completeness audit before expanding non-D sitemaps. Require verified entity identifiers, reliable source references, useful record fields and distinct intent. Repair placeholder identities and classify historical amendments with a dry-run, accession-scoped reconciliation against SEC indexes. The new parser prevents future misclassification but does not silently alter production history. Numeric CRD shape alone does not prove identity. Separate entity identifiers and provenance in a future reviewed migration.

Do not launch city × industry × year filter combinations. Monthly research is conditional on documented coverage and reproducible count definitions. A filing is a submission, not a unique economic event. No aggregate “capital raised” metric is defensible here without offering-level linkage and correction handling.

## F. Measured performance

Environment: local Django test client, SQLite, 100 synthetic issuers, 2,000 Form D records with 10KB raw XML each; same fixture before/after. Seven requests per path/cache mode; median elapsed server-render duration includes query capture overhead. Cold clears Django cache before each request; warm clears once then requests seven times. This is **not browser TTFB, production PostgreSQL, or Core Web Vitals**. Compare `performance-before.json` and `performance-after.json` for exact outputs and HTML sizes.

| Page | Warm queries before → after | Cold median ms before → after | Warm median ms before → after |
|---|---:|---:|---:|
| Home | 3 → 1 | 4.19 → 10.41 | 3.93 → 3.14 |
| California | 8 → 6 | 16.16 → 14.37 | 14.89 → 13.15 |
| Biotechnology | 6 → 4 | 14.02 → 12.67 | 13.67 → 12.73 |
| Issuer | 16 → 12 | 6.37 → 5.78 | 5.63 → 6.16 |
| Filing | 3 → 3 | 2.49 → 2.60 | 2.38 → 2.42 |

Issuer and filing XML-select counts fall from 2 to 0. A cached homepage avoids two category queries. The first uncached homepage is slower because richer grouped counts cost more than distinct category lists; directory data expires after 15 minutes, and each web worker can incur a miss with the default local-memory cache. Issuer warm and filing timings are slightly slower despite less query/data work. Do not describe this as a universal speedup. Richer HTML also adds small payloads. The later adviser compatibility change does not affect these measured Form D paths.

Reproduction: run `.venv/bin/python scripts/benchmark_research.py` from the repository root; it creates and removes its own SQLite fixture and never connects to the configured database. For the original paired measurement, in an isolated checkout/database at the baseline and branch, seed 100 issuers and 2,000 filings (dates 2026-10-21 minus row index modulo 730; every third record D/A; 10KB XML), then use `django.test.Client` and `CaptureQueriesContext` for the five paths in the JSON, seven cold and warm iterations. Use the same article set, settings and fixture across commits; record machine/DB/cache settings. Do not benchmark production with synthetic writes.

CSS is compiled and served by the existing static setup; no new client library, image, font or script was added. Existing third-party resources and ad behavior were preserved. Field CWV was unavailable, so no LCP/INP/CLS improvement is claimed. Next performance work should collect a controlled mobile browser baseline and production query timings, then examine fonts/third-party requests and cache-miss cost. Do not weaken essential ads/consent functionality for a score.

## G. Indexing and analytics findings

Search Console access works for domain property `formdexplorer.com`. The user reported successful sitemap-index processing. At this session's check, Page indexing and the broader Performance report were **processing data**; indexed-page totals and exclusion reasons were not available. The 24-hour performance view reported **0 clicks and 0 impressions**, with a displayed update roughly 4.5 hours earlier. This is the reported window, not evidence of zero indexed URLs or a permanent absence of search traffic. No query/device winners can be identified yet.

An earlier live sitemap validation in this task observed 188,960 canonical content URLs, but submission counts and Google-indexed counts are different measurements. Ingestion changes the inventory; record timestamps for future comparisons.

Cloudflare traffic is not verified human acquisition. The earlier six-hour comparison showed visits falling from 62.44k to 19.16k and requests from 101.25k to 34.14k, alongside large crawler declines (PerplexityBot 33.22k to 3.92k; Shap 4.67k to 1.22k). The 24-hour view still showed visits up 167.7%. These observations support a bot-volume explanation for that window, not proof of a 70% loss of people or Google traffic. The user's approximately 3.14M monthly unique-visitor figure remains unverified as humans. See [Cloudflare metric definitions](https://developers.cloudflare.com/analytics/account-and-zone-analytics/zone-analytics/).

No Google Analytics implementation was found in the inspected repository. Search sessions, engaged/returning users, source-attributed registrations, paid exports and revenue are therefore **unavailable as a joined acquisition funnel**. Existing application/payment records may provide totals, but totals alone do not attribute revenue to organic search. Bot scores and comprehensive production request logs were not exported for a full human/bot estimate. No tracking integration, consent expansion or production credential change was made.

### Repeatable weekly reporting

Use `measurement-template.csv`. Every observation must include source, property, exact date range/timezone, filters, freshness and availability status. Compare complete matching periods; retain raw exports in access-controlled storage. Do not add private customer or payment data to this public repository.

- GSC: Web search, same property/filter set; report clicks, impressions, weighted CTR (total clicks / total impressions), average position with its limitations, query/page/device breakdowns, and branded/nonbranded definitions. Use 28 complete days vs prior 28 once enough data exists. Keep 24-hour preliminary data separate.
- Indexing: total indexed, submitted inventory and indexed submitted pages only where Google provides those scopes; exclusions by reason. Inspect a small sample per template and source quality. Track canonical disagreements and discovered/crawled-not-indexed separately; repair evidence-backed problems rather than mass-request indexing.
- Cloudflare: requests, named crawlers, error rates and origin latency. Treat unknown automation as unknown; do not call every bot malicious. Never substitute “visits” for organic sessions.
- After an approved analytics implementation: capture search use, issuer/filing navigation, registration completion and successful paid export. Use a documented session/consent definition, no personal search terms or email in events, and stable event IDs to deduplicate payment confirmations. Reconcile paid conversions to the payment system, excluding tests/refunds as defined.
- Review actual search landing-page engagement and downstream conversions when available. Do not optimize against impression growth alone. Record deployment dates and content changes alongside results.

## H. 30/60/90-day strategy

| Window | Work and dependency | Measurable outcome / decision |
|---|---|---|
| Days 1–30 | Review/release this PR; verify web and ingestion versions; run live smoke; wait for GSC processing; inventory source-quality defects; define analytics/consent needs | All release checks pass; dated GSC baseline or explicit unavailable status; sample at least 10 records per major family; report verified vs unresolved identifiers and amendment mismatches. Establish funnel definitions before asserting conversion rates. |
| Days 31–60 | Dry-run then reviewed historical classification/identifier repair; refresh highest-priority guides; examine Google exclusion samples; implement approved acquisition tracking; collect production/mobile performance baseline | Compare complete 28-day windows where available; report eligible/indexed counts by family, nonbrand clicks, search use and verified conversions. Publish only quality-approved pages; no fixed traffic-growth promise. |
| Days 61–90 | Expand qualified ADV/CF/Reg A discovery only if coverage passes; publish first reproducible disclosure-count research; improve pages with actual impressions but weak engagement | Measure incremental useful indexed pages, relevant-query clicks, engaged research sessions, returning researchers and attributed paid exports. Stop or revise page patterns that attract irrelevant traffic or fail quality checks. |

## I. Next 10 opportunities

Scores are engineering/product judgments from 1–5; higher impact/confidence/value is better, higher effort/risk is harder. See `backlog.md` for the original pre-implementation ranking. This is the remaining backlog, not promised results.

| Rank | Next action | Impact | Confidence | Effort | Risk | Business value |
|---|---|---:|---:|---:|---:|---:|
| 1 | Reconcile historical Form D/D/A against SEC indexes with dry-run, source provenance and reversible updates | 5 | 5 | 3 | 3 | 5 |
| 2 | Resolve legacy adviser SEC-number/CRD identities; separate identifier fields and deduplicate only with proof | 5 | 5 | 4 | 4 | 5 |
| 3 | Audit/fix placeholder and incomplete CF/Reg A records; shared quality eligibility before new sitemaps | 5 | 5 | 3 | 3 | 5 |
| 4 | Establish trustworthy organic session → registration/export attribution with consent and payment reconciliation | 5 | 4 | 3 | 3 | 5 |
| 5 | Use available GSC exclusion samples to repair actual canonical/discovery/content problems | 5 | 4 | 2 | 2 | 5 |
| 6 | Add importer completeness, freshness and parse-failure reporting by filing type/date | 4 | 5 | 3 | 2 | 5 |
| 7 | Profile production aggregate queries/cache misses and mobile CWV; optimize measured bottlenecks | 4 | 4 | 3 | 2 | 4 |
| 8 | Refresh high-intent existing reading/amendment guides with verified filing examples | 4 | 4 | 2 | 2 | 4 |
| 9 | Build qualified ADV/CF/Reg A editorial landing pages and incremental sitemap sections | 4 | 3 | 3 | 3 | 4 |
| 10 | Publish reproducible monthly disclosure-activity research after coverage validation | 4 | 3 | 4 | 3 | 5 |

Implementation completion is not evidence of organic growth. Measure indexing, relevance and business outcomes after release.
