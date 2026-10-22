# Technical SEO foundation and launch guide

Audit date: October 21, 2026 (America/Los_Angeles). Target: qualified organic visitors researching SEC Form D filings, issuers, private offerings, and filing explanations at **https://formdexplorer.com**.

## Observed baseline

The audit used public HTTP requests, rendered HTML/XML parsing, repository inspection, and read-only Railway configuration. Search Console, DNS ownership and real-user Core Web Vitals were not available; their status is unverified, not assumed absent.

| Area | Observed issue | Implementation |
| --- | --- | --- |
| Sitemap | Live `/sitemap.xml` returned one 14,474-URL document, roughly 2.27 MB uncompressed, with no index. Each large database section was limited to its first 5,000 records. | Sitemap index links every batch of each section; each section has at most 5,000 URLs. URLs always use `SITE_URL`, regardless of request host. |
| Thin/duplicate URLs | Empty industries and paginated hubs were advertised; page 2 canonicals pointed to page 1. | Only populated hubs and issuers with Form D filings enter the sitemap. Later collection pages are self-canonical, `noindex, follow`, linked with ordinary anchors, and excluded from sitemaps. Invalid page numbers return 404. |
| Canonicals | Homepage had no canonical. `www` and the Railway hostname returned duplicate 200 pages. | Every full HTML page has a canonical; known aliases can 301 to the primary origin. Unrecognized production hosts receive `noindex`. Old issuer slugs and lowercase state codes 301 to their canonical paths. |
| Crawl policy | `/search/` was blocked in robots.txt, preventing Google from seeing its existing noindex tag. Fragments and several utility surfaces lacked headers. | Permit crawling search pages so noindex can be read; add shared HTML/header rules for utility pages, fragments and errors. Authentication remains the privacy boundary. |
| Titles/snippets | State titles used only abbreviations; pagination repeated titles. | State names in titles/descriptions, page numbers in paginated titles/descriptions, clearer guides title. Existing issuer, filing and article metadata preserved. |
| Structured data | JSON-LD was assembled in templates; article/issuer strings used JS escaping. Site organization claimed an unverified `sameAs` identity. | JSON-serialized Website/Organization/Article/BreadcrumbList graph, escaped for safe embedding; remove unverified identity link. No invented ratings or rich-result claims. |
| Editorial dates | Every `seed_articles` deployment reset publication and modification dates; future-dated articles were publicly visible. | Preserve publication dates and update modification dates only when content changes. Future/draft articles return 404; blank articles are noindex and omitted from listings/sitemaps. |
| Discovery/performance | Homepage lacked state browsing. Issuer view created a paginator but rendered every filing. | Add populated state links and guide context, show related filing links, render only 50 issuer filings with next/previous links. Defer unused raw XML on list queries and in sitemaps. Cache only public sitemap XML for 15 minutes. |

The live homepage already served HTML without needing JavaScript, had a responsive viewport, gzip delivery, deferred HTMX, Google Fonts `display=swap`, preconnects, and stylesheet delivery through WhiteNoise. HTTP redirected to HTTPS. These are useful foundations and were retained. One-off response times were approximately 0.8 seconds for home, 0.5 seconds for a category and 2.3 seconds for the old sitemap; these are request observations, **not** Core Web Vitals or a controlled benchmark. No traffic/ranking baseline can be inferred from them.

## Indexing policy

- Index: homepage, recent filings, populated first-page industry/state hubs, issuer histories with Form D filings, individual Form D filings with a named issuer, published nonblank guides, API documentation, pricing and legal pages.
- Crawl but noindex: Form D/ADV/CF/Reg A search screens and filters, page 2+ of Form D category/issuer collections, person-name aggregations (names do not uniquely identify people), empty hubs/issuers/articles, login/signup/account, saved searches/watchlists, exports, checkout, API responses, feeds, newsletter actions, HTMX fragments and errors.
- Existing ADV/CF/Reg A **detail** pages retain their metadata/indexability, but are not added to this Form D-focused sitemap. Evaluate their coverage and content separately before expanding sitemaps.
- Draft/future articles and invalid collection page numbers return 404. Search utility pages stay out of the sitemap. Tracking parameters are removed from canonical URLs, while meaningful collection page numbers are retained.
- Individual filings and issuer history pages serve distinct research needs and keep separate canonicals. Amendments remain separate records. A later collection page is not declared a duplicate of page one; its noindex is an intentional conservative quality policy. Direct filing sitemaps provide discovery even if Google visits noindex collections less often.
- `robots.txt` disallows only `/admin/`; it is not access control. Do not add search/private disallows in place of noindex. Protected views must continue enforcing authentication.
- Do not invent word-count thresholds for real filing records. Sparse or incorrect records flagged by Search Console need a content/data review. Sitemap inclusion is a discovery hint, not an indexing guarantee.

## Railway rollout

Verified service: **FormDExplorer → loyal-warmth → production → web**.

- Project: `94b00042-a033-4c97-81e9-232859b3afa9`
- Environment: `47382bf3-275b-4821-b000-8a47a580980f`
- Service: `0a41d75c-1a1e-44f8-b741-6bd7f2900096`
- Source: `Luketheprogram/formdexplorer`, branch `main`. Main updates can deploy automatically; review this change before merging.
- Both apex and `www` custom domains point to port 8080. The service also exposes `web-production-04137.up.railway.app`.
- Railway reports Railpack while `railway.json` selects Nixpacks and `nixpacks.toml` builds Tailwind/collects static files. Keep the existing setup; confirm the effective build steps in release logs. No new package, migration, or ingestion-service change is required.

Set/review these on **web**, not the database or ingestion cron:

```dotenv
SITE_URL=https://formdexplorer.com
DEBUG=False
SEO_INDEXING_ENABLED=True
CANONICAL_REDIRECT_HOSTS=www.formdexplorer.com,web-production-04137.up.railway.app
```

`ALLOWED_HOSTS` must allow the apex and configured aliases (retain any required internal health-check hosts). Keep existing secret/payment/database settings. `SITE_URL` accepts an origin only; a trailing slash is normalized. `SEO_INDEXING_ENABLED` defaults to `not DEBUG` for compatibility with existing production. Set it **explicitly False on every staging/preview environment**, including previews that reuse the production origin. Unknown production hosts also get noindex. The default redirect alias is `www.formdexplorer.com`; include the production Railway hostname as above to consolidate it too.

Only GET/HEAD requests on configured aliases redirect; `/api/`, `/stripe/` and `/admin/` are exempt. POST requests are never redirected across hosts by this middleware. The existing Django HTTPS redirect remains in place, so an HTTP alias may take two hops.

Before merging, run:

```sh
python manage.py check
python manage.py test --noinput
python manage.py makemigrations --check --dry-run
```

The SEO tests exercise complete sitemap batches, exclusion rules, safe JSON, canonical URLs, bounded pagination, redirects, future articles, stable seed dates, verification tags, and staging protection. Tests run with SQLite; PostgreSQL production query performance and the release build still need observation. `makemigrations --check --dry-run` currently reports pre-existing primary-key/index drift in advisers, content, crowdfunding and rega. The same output was reproduced from the unchanged base commit `280bbb9`; this SEO change introduces no model field/index changes and does not generate unrelated migrations. Resolve that existing drift separately before treating the migration check as a clean release gate.

After release:

1. Confirm successful web deployment, migrations/seed completion and Tailwind/collectstatic execution. Existing classes are reused; no new asset pipeline is introduced.
2. Check `/`, `/learn/`, a populated issuer, a filing and `/state/CA/`: 200, canonical `https://formdexplorer.com/...`, one descriptive title and description, no unintended noindex.
3. Check both alternate hosts: public GETs 301 to the corresponding apex path with query strings preserved. Verify HTTP-to-HTTPS and TLS.
4. Fetch `/robots.txt`, `/sitemap.xml` and every child sitemap, including `?p=2` and the final batch. All must be 200 XML/plain text as appropriate, contain only apex HTTPS URLs, and have no utility/empty/paginated collection URLs. A sitemap's own `X-Robots-Tag: noindex` is normal; it does not prevent discovery of its listed pages.
5. Check a collection `?page=2`: 200, self-canonical including `?page=2`, noindex, previous/next links; invalid pages: 404. Search and login must be noindex but accessible for crawling. Private pages must still require login.
6. Use Google's Rich Results Test for an article and Schema.org validator for the graph; structured data must match visible content. WebSite/Organization markup does not promise a rich result.
7. Smoke-test search/HTMX, login, account and export/checkout navigation. Check Railway error rate, slow requests and memory for at least the first ingestion cycle.

Sitemap XML can be 15 minutes behind ingestion. Cache is Django's default per-process memory cache, not shared Redis; each Gunicorn worker warms independently. Never extend this caching to personalized HTML without a separate privacy-aware design. Issuer/filing `updated_at` values are intentionally not published as sitemap lastmod because ingestion/enrichment can touch them without significant content changes. Articles do publish lastmod after the seeding fix.

Rollback: revert this change and redeploy the prior web commit; no database rollback is required. Remove a redirect alias if an integration depends on that hostname. Do not turn production indexing off as a routine rollback: that would emit site-wide noindex.

## Google Search Console: verification and submission

1. Open [Google Search Console](https://search.google.com/search-console) using the owner's Google account. Add a **Domain** property named `formdexplorer.com` (no protocol or path). If it already exists, request access from its verified owner rather than creating redundant work.
2. Copy Google's exact DNS TXT verification value. Add it at the root (`@`, or the provider's equivalent) in the domain's **authoritative DNS provider**, which may be the registrar or a separate DNS service. Preserve existing DNS records; this is an additional TXT record, not a replacement for Railway routing.
3. Click **Verify** after DNS propagation. Leave the TXT record in place permanently; Google checks continued ownership. Railway hosting by itself does not verify Search Console ownership.
4. If DNS access is unavailable, create a **URL-prefix** property for `https://formdexplorer.com/` and choose **HTML tag**. Put only the real tag's `content` value in Railway `GOOGLE_SITE_VERIFICATION` on web, redeploy, confirm the meta tag is present in the unauthenticated homepage HTML, then verify. This fallback covers that prefix; it is not Domain-property verification. Do not use the AdSense publisher ID as this token.
5. After the SEO release passes the checks above, open **Sitemaps** and submit `https://formdexplorer.com/sitemap.xml`. It is the sitemap index; Google can discover its child sections and all batches. Reuse this URL rather than submitting every filing individually. Check that status becomes **Success**, and inspect any child fetch errors.
6. Use **URL inspection → Test live URL** on the homepage, one guide, one populated industry/state page, one issuer and one filing. Confirm indexing is allowed and the declared canonical is correct; after indexing, compare Google's selected canonical. Request indexing for a small representative set of priority pages.
7. Inspect **Page indexing**, **HTTPS**, **Core Web Vitals**, **Manual actions** and **Security issues**. Expected exclusions include deliberate noindex collections/utilities and canonical aliases. Investigate unexpected errors or exclusions on sitemap-listed pages rather than trying to make every URL indexed.

No Search Console account property, verification token, DNS record, or sitemap submission has been created by this code change. Those steps require the actual Google/DNS account and, for HTML verification, Google's issued token. Do not delete existing verification methods.

## Measuring qualified organic growth

Capture a baseline when Search Console becomes available; there is no fabricated starting traffic number. Record release date and compare equal windows with the same filters. Review weekly for the first month, then use 28-day comparisons and a 90-day trend.

| Measure | Where / segmentation | What to do with it |
| --- | --- | --- |
| Sitemap health | Sitemaps: index/section success, discovered counts, fetch errors | Fix failed batches and unexpected omissions first. Counts should reflect eligible database rows, not every site URL. |
| Index coverage | Page indexing, filtered by submitted sitemap | Sample excluded issuer/filing/guide URLs. Investigate canonical conflicts, soft 404s, server errors and low-value data. Deliberate noindex is expected. |
| Nonbrand discovery | Performance → Search results: clicks, impressions, CTR, average position; exclude variations of “Form D Explorer” | Separate issuer-name queries, filing research queries and educational queries. Prioritize relevant pages with rising impressions but weak snippets. |
| Landing-page quality | Compare `/learn/`, `/issuer/`, `/filing/`, `/industry/`, `/state/` segments | Favor visitors researching filings or issuers over generic finance traffic. Examine pages and query intent together. |
| Business outcomes | Existing analytics if available: organic landing → search → issuer/filing view → signup → export purchase | Establish this funnel before claiming commercial ROI. No analytics integration, cookies or conversion tracking is silently installed here. Keep names, emails, CIK query strings and other user-entered search data out of analytics event payloads. |
| Experience | Search Console Core Web Vitals + PageSpeed Insights mobile and desktop on representative templates | Target LCP ≤2.5 s, INP ≤200 ms, CLS ≤0.1 at the 75th percentile. Low-traffic pages may lack field data; use lab results diagnostically, not as field proof. |
| Server load | Railway web errors, latency and memory, especially around crawler bursts/ingestion | Check that bounded sitemaps and issuer pages avoid timeouts. Benchmark production PostgreSQL before adding indexes or caching personalized views. |

Follow-up performance work should be driven by measurements: self-host/subset fonts if they delay rendering, inspect third-party requests, and profile category aggregates on production-scale data. The current foundation keeps content server-rendered and lists bounded. It does not claim a Lighthouse score, rankings, a Core Web Vitals pass or guaranteed growth.

## Primary guidance

- [Google: build and submit sitemaps](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
- [Google: robots meta and X-Robots-Tag](https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag)
- [Google: pagination and crawlable links](https://developers.google.com/search/docs/specialty/ecommerce/pagination-and-incremental-page-loading)
- [Search Console: verify ownership](https://support.google.com/webmasters/answer/9008080)
- [Google: Core Web Vitals](https://developers.google.com/search/docs/appearance/core-web-vitals)
