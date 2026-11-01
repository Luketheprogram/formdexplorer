# Form D Explorer — content quality and AdSense readiness

> Release update — November 1, 2026: the overhaul is now deployed on production commit `a1c5cc361fcf10a002702cda4306981920f66473`; the new public routes and corrected guides returned HTTP 200. The reviewed release passed all 246 PostgreSQL tests without skips. Migration drift was resolved using metadata-only ID labels and the existing index names. Three curated October research editions and their frozen real-data snapshot were then prepared and passed a 250-test PostgreSQL suite. Advertising remains disabled; no AdSense review has been submitted. The original pre-release assessment below is retained as historical context; deployment and PostgreSQL validation are no longer outstanding.

Assessment date: November 1, 2026. Implementation branch: `codex/adsense-content-quality`.

**NEARLY READY — SPECIFIC ISSUES REMAIN.** The changes described here are implemented and locally validated. They have not been deployed, and no AdSense review was requested. Production must receive the reviewed changes and updated article bodies, then pass the release checks below. This assessment is not a prediction of Google's decision.

## A. Original diagnosis

### Confirmed observations

- The existing November 1 rejection screenshot shows **Low value content**, with site ownership verified. It does not identify the individual pages that caused the decision.
- The application is Django 5, server-rendered templates, HTMX, PostgreSQL in production, WhiteNoise/Gunicorn, Tailwind and Stripe/dj-stripe. It is not a client-only application requiring a new rendering framework.
- A read-only live audit found the homepage, guides, California and biotechnology directories, all four search tools, pricing, privacy, terms and login accessible. Canonical URLs matched their public routes. Utility searches and login were noindex as intended. Robots allowed public crawling, the sitemap index responded successfully, and the publisher-verification meta tag and ads.txt were present. These were not confirmed causes of rejection.
- The live site had no `/research/`, computed-report, coverage, standalone publisher or editorial routes; those URLs returned 404. Existing category pages provided useful listings and basic counts, but lacked monthly comparisons. Issuer pages supplied histories and a latest snapshot without a disclosure-difference viewer.
- Several guide bodies needed substantive corrections. Examples included describing sold amounts as cash raised, treating both Form D and Form 1-A as registration, oversimplifying purchaser verification, implying adviser strategy or track record from assets/headcount, and suggesting stronger entity relationships than a name match establishes. These findings came from the actual source text, not a generic SEO checklist.
- Publisher identity, methodology and consent-gated advertising already existed. Those systems were preserved and made easier to discover. No replacement identity, credentials or publisher ID was invented.
- Substantial pre-existing uncommitted import, alert, account and accuracy work was present. It remains in the checkout. This implementation did not change those pipelines, payment settings or schemas.

### Evidence-supported interpretation

The most plausible content concern is that much of the indexable experience repackaged individual SEC fields, while original analytical functionality was limited and some educational interpretation was unreliable. The exact weighting Google applied is unknown. A new title, more advertisements or a large volume of generated text would not establish the missing value.

Policy baseline: Google's [content-quality and navigation guidance](https://support.google.com/adsense/answer/81904?hl=en), [publisher-content inventory policy](https://support.google.com/publisherpolicies/answer/11112688?hl=en), and [people-first content guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content). These emphasize useful original content, a usable experience and appropriate inventory; they do not guarantee acceptance after any particular change.

Public observations are recorded in [live-before.json](../outputs/adsense-quality/live-before.json). The audit covers representative route families, not every production record or all external links.

## B. Selected ten improvements

One hundred distinct candidates were considered privately. Only these ten are retained. Ratings use 0–5 per criterion: 0 = harmful/unsupported, 1 = weak, 2 = limited, 3 = useful, 4 = strong, 5 = strongest fit. Higher risk ratings mean **lower implementation risk**. Weighted score = original value × 0.30 + rejection relevance × 0.25 + feasibility × 0.15 + low risk × 0.10 + usability/performance × 0.10 + maintainability × 0.10. Scores are prioritization judgments, not measured site quality or Google approval probabilities.

| Selected intervention | Weighted score / 5 | Why it outperformed alternatives |
|---|---:|---|
| Original monthly filing and amendment research | 4.75 | Adds reproducible analysis over existing records without asserting financing outcomes or manufacturing articles. |
| Source-linked issuer disclosure comparisons | 4.75 | Makes histories materially more useful; avoids fabricated company narratives and unsupported offering chains. |
| Route-family quality audit and selective empty-page handling | 4.60 | Addresses actual sparse-content cases while preserving working search and established URLs. |
| Correct and source the existing educational guides | 4.75 | Removes confirmed errors and improves real research workflows at established URLs. |
| Cached category trends and dataset context | 4.50 | Adds useful comparisons with explicit denominators and coverage limits, avoiding market extrapolation. |
| Interactive state/industry and filing comparisons | 4.60 | Supports research tasks with existing infrastructure, rather than decorative calculators or new services. |
| Live coverage and factual publisher/editorial transparency | 4.60 | Lets readers inspect scope, sourcing and correction procedures without invented credibility. |
| Research navigation and accessible workflows | 4.45 | Connects search, profiles, guides and tools with minimal design disruption. |
| Canonical research discovery and proportionate indexing | 4.45 | Extends already functioning SEO infrastructure and fixes identity-empty category discovery. |
| Repeatable, fail-closed AdSense readiness checks | 4.60 | Makes configuration and human dependencies reviewable without enabling ads or claiming certification. |

Content manufacturing, unsupported financial inference, broad deindexing, cosmetic credibility and monetization-first changes were rejected. No full brainstorm or additional candidate list is published.

## C. Implemented changes

All items below are implemented **in source**. Production rollout and account-specific checks are still outstanding.

| Improvement | Changes and principal files | Added value and status |
|---|---|---|
| 1. Research section | `filings/intelligence.py`, `filings/research_views.py`, `templates/research/hub.html`, `report.html`, monthly/coverage/availability partials; routes in `filings/urls.py` | Two flagship computed reports: `/research/filing-activity/` and `/research/amendments/`. Twelve monthly buckets, initial/amended notices, distinct CIKs, completed-calendar-month differences, amendment shares and numeric-field availability. No dollar totals, forecasts or unsupported editorial conclusions. Implemented. |
| 2. Issuer profiles | `filings/views.py`, `templates/filings/issuer_detail.html`, `templates/research/_changes.html` | Compare two latest source disclosures, including offered, sold, investor count and minimum investment. Original histories, source links, cross-filing records, reviewed identity/year notes, contacts and follow controls remain accessible. Implemented. |
| 3. Page quality | `filings/readiness.py`, `audit_content_quality` command, category views and sitemaps | Read-only route classification and stored-content audit. Categories containing only blank issuer identities are noindex and omitted from category sitemaps. Empty computed reports are noindex and omitted from discovery; sparse but usable categories are retained. No records or route families deleted. Implemented. |
| 4. Educational content | `content/reviewed_guides.py`, `content/research_guides.py`, existing `seed_articles` command, `templates/content/article_detail.html` | Replaces the ten built-in guide bodies at existing slugs, expands methodology, adds primary citations and worked workflows, and shows actual publication/update dates with publisher attribution. The field-reading guide uses an SEC-verified BigHat accession and explicitly separates arithmetic from financing conclusions. Implemented; article reseeding required on release. |
| 5. State/industry depth | `category_report` in `filings/intelligence.py`, category views/templates, monthly/period partials | Page-one monthly histories, prior-completed-month comparisons and share of eligible dataset filings using the same month as denominator. Current stored issuer address and per-filing industry limitations are disclosed. Existing filing lists and pagination remain. Implemented. |
| 6. Interactive tools | `/research/compare/`, `/research/filing-changes/`, corresponding views/templates | Compare populated states or industries with aligned months and definitions. Choose two accessions for one CIK, up to the latest 200 records. Invalid selections receive useful errors; single-category/single-filing cases explain the missing prerequisites. Utilities stay noindex. Implemented. |
| 7. Transparency | `content/trust_views.py`, `templates/content/about.html`, `editorial.html`, `templates/research/coverage.html`, `config/urls.py` | Standalone publisher/contact, editorial/corrections and computed coverage pages. Uses existing published operator/contact details. Distinguishes record modification from import completeness, reported data from calculations and computed tables from human commentary. Implemented. |
| 8. Workflows/accessibility | `templates/base.html`, homepage, profile/category/article links, `static/css/research.css` | Research in desktop/mobile navigation and footer; links from profiles to comparisons and guides; keyboard skip link; labeled forms; tables with captions/column and row headers; focusable scrolling regions; readable small-text contrast. A confirmed 320px category-grid overflow was fixed. Implemented. |
| 9. Technical SEO | `filings/sitemaps.py`, `filings/templatetags/seo.py`, report views, existing middleware retained | Adds populated canonical reports and factual transparency pages to discovery, visible matching research breadcrumbs to structured data, and selective empty-state noindex. No invented Dataset schema, bulk URL rewriting, crawler blocking or broad category deindexing. Misleading recent-page financing metadata was corrected. Implemented. |
| 10. Readiness/operations | `audit_adsense_readiness` command, `filings/readiness.py`, public audit/preview/benchmark scripts, tests, README and this report | Reports local configuration, reviewed-content availability and manual account/consent/release actions without printing secrets or mutating state. Existing publisher verification, ads.txt, editorial-only placements and consent gates remain unchanged. Local audit implemented; real account and regional CMP certification remain manual. |

### Calculation safeguards

- A unique accession is the filing unit; a distinct stored CIK is the issuer unit. Counts are not financing-round counts.
- An amendment is `form_type == D/A` **or** an extracted amendment flag. It is counted once, even when both are true.
- No offered/sold amounts are summed. Arithmetic differences compare dated disclosures and never establish common offering identity, cash receipt or new investors.
- Missing/invalid negative values are unavailable; reported numeric zero is retained. Same-day directional differences are suppressed because stored dates do not establish sequence.
- Monthly histories include twelve calendar months and explicitly label the partial current month. Comparisons use the preceding two completed calendar months; completed calendars do not certify complete imports. Percentage changes with zero denominators are unavailable.
- Analytical scope excludes blank issuer names and future-dated filings, while source records remain available through established tools. Monthly distinct-issuer counts are not added into annual issuer totals.
- Public aggregates are cached for fifteen minutes using finite validated scopes and safe cache keys. No new view downloads SEC records, fetches enrichment or introduces a service/dependency. Raw XML is excluded from report queries.

The real example was checked against [SEC accession 0001231919-26-001499](https://www.sec.gov/Archives/edgar/data/1797256/000123191926001499/0001231919-26-001499-index.htm) and its [primary disclosure](https://www.sec.gov/Archives/edgar/data/1797256/000123191926001499/xslFormDX01/primary_doc.xml). Requirements were checked against the official [506(b)](https://www.sec.gov/resources-small-businesses/exempt-offerings/private-placements-rule-506b), [506(c)](https://www.sec.gov/resources-small-businesses/exempt-offerings/general-solicitation-rule-506c), [Form D notice](https://www.sec.gov/resources-small-businesses/exempt-offerings/filing-form-d-notice), [Regulation Crowdfunding](https://www.sec.gov/resources-small-businesses/exempt-offerings/regulation-crowdfunding), [Regulation A](https://www.sec.gov/resources-small-businesses/exempt-offerings/regulation) and [Form ADV](https://www.investor.gov/introduction-investing/investing-basics/glossary/form-adv) resources.

## D. Before-and-after assessment

These are qualitative comparisons of the original repository/live pages with the implemented local version. They do not imply the changes are already live.

| Dimension | Before | Implemented version |
|---|---|---|
| Original research | Basic counts and raw-record exploration | Two computed reports, scope/freshness disclosure and reproducible comparisons |
| Issuer usefulness | History, counts and one latest snapshot | Source-linked field differences with missing-value and sequence safeguards |
| Directory depth | Lists, totals and category leaders | Monthly context, completed-period differences and dataset-relative shares |
| Education | Useful starting material with confirmed misleading interpretations | Corrected existing guides, primary citations, a verified example, worked workflows and transparent dates |
| Navigation | Search tools and guides | Connected research hub, comparison tools, category/profile handoffs and keyboard navigation |
| Publisher credibility | Identity within the guide listing; methodology existed | Dedicated factual publisher, editorial/corrections and current coverage pages |
| Indexing health | Functional canonical/robots/sitemaps and selective noindex | Preserved foundation plus aligned research discovery and identity-empty category exclusions |
| AdSense readiness | Ownership verification/ads.txt worked; low-value rejection remained | Stronger content and tools with repeatable local checks; deployment and genuine account/consent checks remain |

## E. Verification results

- Complete Django suite: **252 tests, 21 skips, no failures**. Includes the existing search/filter, account, export, payment/webhook, API, ingestion, identity-review, alert and SEO suites, plus 20 new research tests. This is local SQLite regression evidence, not a live payment or production export test. Skips primarily require PostgreSQL locking/concurrency features.
- Baseline: 232 tests, 21 skips, two sandbox-denied local SMTP listener errors. With loopback permitted, those tests and the full amended suite pass.
- Financial cases cover amendment flag/type combinations, missing/zero/negative fields, same-day and reverse chronology, cross-issuer selections, duplicate join rows, monthly boundaries/year rollover/leap year, future dates, distinct issuer scopes and zero denominators.
- Browser: **65 route/viewport checks**, 13 public routes at 320, 390, 768, 1024 and 1440px. Research category selection, filing form submission, keyboard skip navigation and mobile menu interactions passed. Checks included one heading/canonical, labeled controls, no document overflow, no ad slots and no JavaScript page errors. All external requests were blocked. This is focused accessibility evidence, not a comprehensive assistive-technology certification.
- Existing advertising browser regressions: **9 passed**, zero failures/skips, using an isolated synthetic SQLite copy with all Google responses intercepted. Covers consent denial/unknown state, GPC, revocation, US opt-out changes, blocked/unfilled ads, mobile dialogs and utility-page isolation. No real CMP certification or ad fill was tested.
- Django `check` and production-mode `check --deploy`: pass. Python compilation, advertising/browser JavaScript syntax and `git diff --check`: pass.
- Tailwind **3.4.17**, as pinned by the repository build: pass. The binary reported an outdated Browserslist database; this did not fail the build. WhiteNoise compressed-manifest `collectstatic` and resolution of the app/research/advertising assets: pass in a disposable output directory.
- Local benchmark: disposable SQLite, 100 issuers/2,000 filings, seven samples per cold/warm route. Warm flagship reports use zero database queries; a cold report uses two aggregate queries. The selected-filing viewer uses two queries. All measured routes select no raw XML. See the exact timings in the benchmark artifact; these are local measurements, not production load tests or Core Web Vitals.
- `makemigrations --check --dry-run` still reports **pre-existing** adviser ID, newsletter-subscriber ID and crowdfunding index/ID drift, matching the earlier held migration-check log. No model change or new migration was introduced by this overhaul. No migration was generated to hide that existing issue.
- Live audit performed unauthenticated GETs only. It confirms the original deployment and existing technical baseline; it cannot validate routes that have not yet been released. No real advertisement was requested or clicked.

Evidence: [Django log](../outputs/adsense-quality/formd-overhaul-final-tests.log), [browser checks](../outputs/adsense-quality/browser-checks.json), [advertising browser log](../outputs/adsense-quality/advertising-browser.log), [benchmark](../outputs/adsense-quality/benchmark.json), [deployment check](../outputs/adsense-quality/deploy-check.txt), [static build](../outputs/adsense-quality/static-build.txt), [desktop report preview](../outputs/adsense-quality/activity-1440.png), [mobile viewer preview](../outputs/adsense-quality/changes-390.png). Preview records are explicitly synthetic and exist only in a disposable local database.

## F. Remaining actions and release notes

1. **Review and integrate the branch with the existing uncommitted work.** Do not commit the entire checkout as though all changes belong to this overhaul. Review the specific files listed above and retain the prior account/import/alert work. No push, merge or deployment was performed.
2. **Review article and publisher text, then release it.** The existing Railway predeploy command runs `seed_articles`. Back up current authored article bodies and timestamps first; this command updates built-in bodies, not just missing articles. It preserves original publication dates and avoids changing modification dates when content is unchanged. Reconcile any newer editorial edits before deployment.
3. **Run the suite on a disposable PostgreSQL database.** Resolve or explicitly accept the existing migration-state drift as a separate reviewed task. Exercise the skipped concurrency checks; never use a production database as the test target.
4. **Deploy the reviewed code through the existing build.** Keep advertising disabled. Check canonical production origin/indexing settings, hashed research assets, new public routes, guide bodies, populated/empty indexability and sitemap contents. Run `audit_content_quality` and `audit_adsense_readiness` in the release environment. The local default origin/indexing and absent publisher settings are development defaults, not production defects.
5. **Inspect production coverage and performance.** Review the coverage page and existing ingestion-health tooling. Check monthly buckets and representative issuer differences against SEC sources. Confirm import gaps before using a report for a market narrative. Run PostgreSQL query plans/load checks at production-like volume and measure actual mobile Core Web Vitals; a 2,000-record SQLite benchmark cannot establish those.
6. **Verify the real account and consent setup.** Domain ownership and the existing public seller record were observed, but account policy status, actual manual-unit ownership, Auto ads disabled and current regional consent behavior require the owner/real account. Preserve `ADSENSE_ENABLED=False` until approval and genuine consent validation. No local audit can certify applicable consent/privacy obligations. Confirm privacy wording reflects actual vendors and operations.
7. **Complete a production smoke test.** Search all four datasets, open representative profiles/source links, sign in, inspect watchlists/saved searches, and test an authorized paid export and checkout flow using the appropriate approved test environment. Existing regression tests do not establish successful live billing or external mail delivery.
8. **Request review manually after the release checks.** The owner should return to the existing AdSense site entry and request review only after reviewing the deployed experience. No automated resubmission has been made.

Rollback: revert only this overhaul's reviewed source changes and rebuild assets; no new schema needs reversing. Article-body updates persist in the database, so restore the pre-release article backup if content must be rolled back. Existing financial, alert and ingestion data must not be deleted. Aggregates expire within fifteen minutes; a rolling deployment can temporarily show different cached coverage until expiration.

## G. Resubmission assessment

**NEARLY READY — SPECIFIC ISSUES REMAIN.** Original research tools, differentiated issuer analysis, corrected guides and factual transparency are implemented with passing local checks. The current public deployment still presents the pre-overhaul experience. Release the reviewed changes, verify production data/flows and resolve the account-specific consent/readiness checks before requesting review. Existing migration drift and the unrun PostgreSQL-specific checks must remain visible in the release decision. No claim is made that these changes guarantee approval.
