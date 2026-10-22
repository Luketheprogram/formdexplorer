# Priority fixes ready for review

Scope: paid access and safe exports first, then parser/identity correctness and search validation. No deployment, production migration, Stripe configuration change, production ingestion, customer email, or production data repair has been performed.

## Behavior changes

- Paid exports and API access require an active account, a known paid tier, and `active` or `trialing` subscription status. `past_due`, `unpaid`, canceled, paused, incomplete, and unknown statuses do not qualify. This intentionally has **no implicit payment grace period**; review this policy before release.
- Subscription handlers record the last event timestamp/ID and subscription ID. Older events cannot restore revoked access; cancellation of a different older subscription cannot revoke a replacement. All same-second events with different IDs reconcile with Stripe's current subscription rather than guessing their order. Invoice failures do not overwrite authoritative subscription state.
- One-time export credits require a `paid` Checkout Session and a payment-intent identity. Both normal completion and asynchronous payment success grant idempotently. A database constraint prevents duplicate nonblank payment intents.
- Export credit consumption is a conditional database update after file generation. A concurrent losing request gets HTTP 409 without a file; generation failures retain the credit. This protects generation, not network delivery: a disconnect after the server commits can still consume a credit.
- XLSX source strings are explicit text cells, and CSV formula-like text is neutralized. Numeric zero and negative numeric values remain numeric. Successful downloads are private/no-store.
- Shared search validation handles browser/API/export/saved-search inputs, comma-formatted whole-dollar amounts, valid dates, numeric bounds, reversed ranges, and JSON multi-select lists. Invalid web searches show feedback in the existing result panel; invalid exports/API calls return controlled 400 responses without consuming an export credit. Invalid legacy saved searches are skipped individually during alert processing, and new invalid saved searches are rejected.
- Parsers preserve zero/false values and avoid floating-point rounding for integer disclosures. Reg A parsing recognizes the observed split legal-identity/address schema and its tier, cash, and security-type fields. Submission type and CIK are reconciled with the SEC index.
- Reg A structured-document discovery falls back to the primary form in the complete submission when `primary_doc.xml` is absent. It does not mistake an exhibit for the primary form. Unsupported unstructured documents are explicitly counted as skipped; download/parse failures are counted as errors. This is **not full HTML-form coverage or a durable retry ledger**.
- A common issuer updater protects known fields from blanks, CIK placeholders, and older filings. It derives a conservative legacy date baseline and preserves populated URL slugs. Older documents can fill missing fields but cannot replace newer known values.
- Adviser disclosure labels use explicit raw source evidence, not legacy Boolean defaults. Unknown is displayed as unknown; name matches are labeled as unverified with confidence. The Reg A blanket assurance claim is replaced with source-verification wording.

## Preserved

The current layout, styling, route structure, canonical rules, sitemap generation, robots policy, indexing exclusions, pricing, and anti-double-counting summaries are preserved. The pre-existing signup redirect changes in the working tree were retained. Other concurrently appearing growth-related files were not edited for this task. No commit or push was made, so Railway cannot auto-deploy these changes from this work.

## Migrations and preflight

Two new migrations are proposed: `accounts/0004_payment_integrity` and `filings/0012_issuer_source_filing_date`. They were exercised only in disposable local test databases.

The payment migration deliberately stops if existing nonblank payment intents are duplicated; it does not delete or merge purchased credits. Before an approved release, inventory duplicate intents and accounts whose paid tier has an empty/nonqualifying status, reconcile them against Stripe, and take a backup. Existing valid active/trialing states continue to qualify. Confirm the webhook endpoint receives `checkout.session.async_payment_succeeded` and the supported subscription events. No webhook settings were changed here.

The account/filing migration state check passes. The adviser initial migration now depends on the filing initial migration, ensuring `pg_trgm` exists before the adviser GIN index on a fresh database; this adds no SQL to already-applied migrations. The repository-wide check also identifies pre-existing default-ID/index-name drift in advisers, content, crowdfunding, and Reg A. Those unrelated schema changes are intentionally excluded.

## Historical repairs are separate and dry-run by default

`repair_filing_data` reads stored XML, never fetches the network, and never updates issuers, slugs, routes, or financial aggregation logic. It corrects explicit Form D submission types/amendment flags and fills previously missing supported numeric/Boolean values. It does not infer D when the source type is absent. Source CIK must agree with the stored issuer.

Start with an accession-specific dry run against a restored staging copy:

```sh
python manage.py repair_filing_data --dataset d --accession 0000950138-26-000034
```

An approved apply requires a new journal path (existing files cannot be overwritten):

```sh
python manage.py repair_filing_data --dataset d --accession 0000950138-26-000034 --apply --journal /safe/reviewed-repair.jsonl
```

These examples are instructions for later review, not commands run against production. Each journal records accession/ID, source hash, before/after values, and a separate commit marker. Writes are bounded to at most 5,000 rows per invocation; default 500. `--after-id` supports deliberate batch continuation. Records without stored XML require a separate reviewed source-retrieval process. No broad issuer rewrite is part of this tool.

Rollback a data batch using the reviewed before-values only where the current values still match that journal's after-values; use the backup when appropriate. A prepared row without a committed marker requires database inspection before retry/rollback. Do not blindly overwrite concurrent corrections. Code rollback can leave these additive columns/constraint in place; do not remove the uniqueness constraint or restore unsafe entitlement logic as an automatic response to unrelated failures.

## Validation and limits

Review on 2026-10-22: **128 tests passed on an isolated PostgreSQL 17.10 database, with no skips.** The database was built from official PostgreSQL source in `/tmp`, accessible only through a local Unix socket, and contained synthetic test data. The suite applied the complete migration chain from scratch.

Additional issues found and fixed during review:

- Simultaneous deliveries of the same Stripe event could race on the event ID and return HTTP 500. The losing insert now rolls back its savepoint and processes the committed event through the idempotent receivers. A deterministic two-connection test forces both inserts to race.
- Same-second events with unchanged status could carry different plans and incorrectly restore API access. Reconciliation now covers plan changes too.
- Test/live mode mismatches are rejected at the custom endpoint and ignored by entitlement receivers, including receivers invoked through dj-stripe's alternative URL.
- Checkout success/cancel URLs were shadowed by the dynamic plan route and could return 404. Fixed the route ordering without changing URLs.
- A new issuer name was bounded only after its first insert, which can fail PostgreSQL's length constraint. It is now bounded before insertion.
- Extremely large API offsets could overflow the database integer range. They now return a controlled 400.
- Fresh PostgreSQL migrations attempted to create the adviser trigram index before its extension. Added the explicit migration dependency.
- Malformed XML could abort a historical repair batch during its strict type check. It is now skipped with a journal entry; repair locks target only the filing row to avoid an opposing issuer/filing lock order with ingestion.

Concurrency coverage includes all five download routes (exactly one HTTP 200/file and one HTTP 409/no file per credit), direct credit consumption, duplicate event IDs, different event IDs for one payment, and simultaneous subscription updates. The legacy-payment migration test proves duplicate detection rolls back the migration without deleting credits, permits multiple blank manual credits, and preserves qualifying existing accounts.

Signed webhook HTTP tests exercise real signature verification, event persistence, application receivers, invalid/expired signatures, mode mismatches, reordered statuses, and rollback/retry after a handler failure. Only dj-stripe's remote account/object mirroring is stubbed. These are **local signed fixtures**, not events delivered by Stripe. The user explicitly deprioritized another external Stripe test and reported a previously successful test; no external test connection, transaction, subscription, or webhook configuration was changed.

Django's production-settings `check --deploy`, the account/filing migration-state check, and `git diff --check` pass. Tests ran with Django 5.2.18, psycopg 3, stripe-python 15.6.1, and dj-stripe 2.11.0. Production dependency versions were not inspected. Desktop and 390px mobile synthetic-data previews were inspected during implementation; this review did not change the design or SEO templates. Existing SEO/advertising regression tests pass in the full suite.

SQLite compatibility: **123 passed, five PostgreSQL-only concurrency tests skipped** (128 discovered). Those five tests all passed on PostgreSQL. The disposable PostgreSQL server was stopped after validation.

Evidence logs: `/tmp/formd-postgres-check.log` and `/tmp/formd-sqlite-review.log`. Reproduce the PostgreSQL run by pointing `DATABASE_URL` at a disposable PostgreSQL database with database-creation and extension privileges, then running `python manage.py test --noinput`. Never point this test command at production. The local-only settings used here are `/tmp/formd_pg_settings.py`.

Production schema/data inventory, backup, and any historical repair remain release-time work. Railway's connected integration exposed variable names only, so production duplicate-payment/account-state data was not inspected. No deployment, production migration, production data write, commit, or push was performed.

Deferred from the broader audit: alert delivery/scheduling, a current ADV bulk refresh, HTML-only Reg A support, a persistent ingestion retry ledger, general search pagination, shared rate limiting, analytics/ads, pricing experiments, and infrastructure changes.
