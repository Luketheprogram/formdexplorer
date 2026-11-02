# Research workbench operations

The release adds original descriptive reports, source evidence, public coverage checks, private collections, owner-scoped background exports, and consent-based feedback. Existing advertising guards and Google CMP settings remain unchanged. Do not enable advertising while AdSense approval is pending.

## Background processing

`RESEARCH_MAINTENANCE_ENABLED=True` starts bounded maintenance inside the existing WSGI application deployment. It uses the application's existing access; no separate service receives production credentials. A PostgreSQL advisory lock elects one active cycle across WSGI processes. Cycles run approximately every five minutes after boot. Job leases and input-version checkpoints recover interrupted work and prevent stale extraction from hiding newer source revisions. Gunicorn must load WSGI after fork, as the current deployment does; do not add `--preload` while this runtime is enabled.

A cycle handles up to twenty queued jobs, then up to 500 source extractions per dataset, daily index reconciliation, an unpublished monthly draft, and retention cleanup. Source recovery requires an explicit staff queue action and shares the ingest pipelines' SEC request lock. It never changes financial fields or issuer identity. Unsupported sources remain held for review. No research is automatically published and no email is sent.

Operators can also run `python manage.py research_maintenance` for one finite cycle or `python manage.py process_research_jobs --limit 5` for queued work only. The staff-only `/research/operations/` dashboard shows import failures, source checks, feedback, aging guides, research jobs, and maintenance heartbeat. Disable the runtime flag to stop periodic cycles; queued records remain durable.

## Exports and private data

Exports are owner-scoped, capped at 5,000 matching records and 10 MB. Larger result sets fail rather than silently truncate. A credit is consumed atomically only after successful generation. Download bytes expire after 24 hours. Completed status/history remains available. Private feedback contact addresses expire after 90 days. Collections and annotations are not public or indexed. Source downloads are inert text attachments.

## Source checks and research publication

The public calendar compares exact stored accession sets against retrieved SEC daily indexes. Unchecked, partial, failed, and scheduled-closure states remain distinct. A quarterly manifest match applies only to that posting; late final-day filings can appear in a subsequent posting. The frozen 2026 Q3 check matched all 15,952 SEC accessions. Its public JSON includes the original URL, checksum and limitations.

Run `python manage.py reconcile_sec_quarter --archive FILE --year YYYY --quarter N --source-url EXACT_SEC_HTTPS_URL --output REPORT.json` against a downloaded official archive. It performs no filing modifications. Source extraction preserves identity as reported, raw values, explicit references, missing/indefinite/invalid/zero distinctions, and estimate qualifiers. Acceptance timestamps are shown only when actually preserved in a source.

Research editions remain drafts until a verified profile and recorded source/calculation/interpretation review are available. Published snapshots are immutable; corrections use a new version and prior-edition reference. The owner currently has no verified personal biographies, named reviewers or consenting usability testers. Do not fabricate profiles, review records or session results.

## Validation and release

The implementation ledger is `docs/implementation-program.json`. It distinguishes shipped software from outstanding human, physical-device and full-data restore evidence. First-party asset budgets are in `docs/performance-budgets.json`; run `python scripts/check_asset_budgets.py`. Desktop constrained-width checks are not physical mobile-device tests or field Core Web Vitals.

Regression tests run against isolated PostgreSQL. `benchmark_research_pg` refuses production and requires an owned local public-data restore with at least 100,000 filings. `scripts/audit_content_links.py` performs a bounded public GET crawl and excludes authenticated/mutation routes. `scripts/check_public_seo.py` provides deployment smoke checks.

The public-data restore rehearsal passed with 197,085 source rows and enrichment blanked. The owner subsequently authorized the full-data restore drill. It restored and checked all 99 production tables (609,916 rows), then deleted the private local database, dump and diagnostics; the sanitized report records success. The sanitized evidence reports are private workspace outputs, not public repository content.

The release uses additive researchdesk migrations. To roll back application behavior, disable maintenance and redeploy the preceding application release; keep the additive tables and source/queue history. Do not reverse database migrations or restore over production as part of a routine code rollback.

## Legacy source metadata audit

Quarterly SEC archives exposed 30,585 historical amendment label/flag mismatches in 2025–2026. Three independently retrieved primary XML documents confirmed the source type. The repair tool changes only filing metadata with the same primary CIK and exact accession; financial values and issuer profiles are unchanged. Conflicting dates require a current SEC index check. All eight inspected date discrepancies were confirmed as the currently stored official dates, so none was overwritten. SEC filing dates can be adjusted independently of acceptance timestamps.

`repair_sec_manifest` defaults to preview. `--apply --metadata-only --verify-date-indexes` applies guarded metadata corrections without queuing new records. Enqueue historical missing accessions only after the alert-suppression code is deployed wherever alerts are processed. The historical marker is durable in the ingestion queue and excludes those records from both alert discovery and delivery eligibility. Existing holds and retry budgets are preserved.
