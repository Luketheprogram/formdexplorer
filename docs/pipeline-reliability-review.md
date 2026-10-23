# Data pipeline reliability — release and operations guide

This patch makes missed SEC indexes and filings recoverable across runs, adds independent freshness checks, and expands Reg A document coverage. It does not apply historical repairs. Authorized ingestion adds newly discovered filings. Templates, styles, routes, canonical metadata, sitemap logic, pricing and existing source values are unchanged.

## What changes

- **Durable recovery:** every requested index date and discovered accession gets a unique database job. Network errors, malformed documents and unsupported schemas retain their error and retry deadline. HTTP requests retry transient failures up to three times; jobs back off from 15 minutes to one day, honor longer `Retry-After` headers, and stop for review after eight attempts. A named command requeues held work with an audit note.
- **Crash/concurrency protection:** expiring job leases allow recovery after a process dies. Lease tokens prevent an old worker from committing after another worker takes over. Filing writes, original-source archival and success checkpoints commit in one transaction. A PostgreSQL advisory lock serializes the three EDGAR pipelines, including separate management-command invocations, to prevent overlapping SEC request bursts. SQLite is for development; production concurrency guarantees are tested on PostgreSQL.
- **Recovery beyond the lookback:** unfinished jobs remain eligible regardless of age. After scheduler downtime, missing dates since the last indexed date are queued automatically. Work is bounded to 100 index jobs and 2,000 filing jobs per dataset per invocation by default. A recent successful index is revisited to discover additions, while already-successful accessions are not rewritten.
- **Coverage:** form names containing spaces (including `1-A POS`) now parse correctly. Reg A adds `1-SA`, `1-SA/A`, `1-A-W`, `1-A-W/A`, `1-Z-W` and `1-Z-W/A`. Form C uses complete-submission XML fallback when `primary_doc.xml` is absent. Malformed XML, unknown required schema containers and conflicting submission types remain unresolved work rather than false successes.
- **Conservative HTML/text support:** Reg A documents without structured XML can create filing records using matching SEC header/index accession, CIK, form and date. Financial fields remain unknown. Existing issuer identity, review records and URL slugs are untouched. Withdrawal filings are discoverable as their own form type; no automatic offering-status inference or cross-issuer linkage is made.
- **Source preservation:** exact retrieved XML, complete submissions and indexes are archived with URL, retrieval time and SHA-256. HTML is never put into `raw_xml`, rendered or used to guess financial values. Routine discovery records existing filings as already present without rewriting them. The existing `--no-raw-xml` flag omits the filing-column copy but does not disable the audit archive or erase existing XML. Documents over 64 MiB are rejected without storing a truncated filing.
- **Independent monitoring:** `check_ingestion_freshness` emits JSON and a failing exit status for missing/stale runs, unresolved old jobs, held work, expired leases, recent run errors and stale SEC index coverage. It checks ingestion activity separately from the latest filing date, so quiet datasets are not falsely stale. Regular SEC holiday 404s are recorded separately; unexpected missing dates remain visible. Exceptional closures require investigation.

## Scheduling

`railway.cron.json` runs `ingest_edgar --days 7` every six hours. The coordinator attempts all three datasets even when one fails. It requests indexes through the previous date in America/New_York. SEC daily indexes are published overnight; more frequent retries do **not** make this a continuous intraday feed.

The independent `ingestion-freshness` Railway cron service uses native service settings: `python manage.py check_ingestion_freshness --report-sentry`, schedule `30 */6 * * *`, restart policy `NEVER`, and no pre-deploy command. Its `DATABASE_URL` and `SECRET_KEY` reference the web service, `DEBUG=False`, and `PGOPTIONS=-c default_transaction_read_only=on`. It follows the same GitHub main branch. Railway no longer allows new services to use legacy JSON configuration, so no monitor JSON file is attached. Existing web/ingestion JSON configurations continue working until Railway's December 1, 2026 cutoff and need a separate configuration migration before then.

Railway account failure/crash rules deliver Email & In-App notifications. Verify delivery with a controlled run using `INGESTION_NOTIFICATION_TEST=1`; this produces an explicitly labeled failure before any database access. Restore the variable to `0`, redeploy and run the monitor again after the test. Never leave probe mode enabled. With a configured `SENTRY_DSN`, `--report-sentry` also emits a grouped error; native Railway failure notifications are the deployed notification path when Sentry is absent.

Default heartbeat tolerance is 36 hours; unresolved-work tolerance is 24 hours. Index freshness uses SEC business days with one publication-day grace. `check_ingestion_freshness --max-age-hours N --backlog-age-hours N` adjusts these thresholds.

## Deliberate limits

- ADV source/write timestamps are included in the report, but ADV coverage is explicitly `refresh_not_instrumented`. This patch does not invent a current bulk source or run the existing, separately managed ADV importer. A verified ADV refresh workflow remains follow-up work.
- HTML financial extraction, automatic withdrawal-to-offering linkage, SEC post-acceptance correction/deletion reconciliation, historic backfills and issuer repairs remain separate reviewed operations. Existing metadata-only rows are not silently enriched.
- Failed/held sources are retained for diagnosis. Source history has no automatic deletion policy in this patch; monitor storage growth before expanding historic ingestion.
- Existing pre-ledger history is not certified complete by a healthy heartbeat. Initial coverage begins with the requested lookback; an older backfill needs a separately reviewed date range.

## Local commands

Use these commands with the intended environment explicitly selected:

```sh
python manage.py migrate
python manage.py ingest_edgar --days 7
python manage.py check_ingestion_freshness
python manage.py retry_ingestion_job JOB_ID --note 'Reviewed cause and recovery'
python manage.py test --noinput
```

A nonzero ingestion exit means unresolved work remains; successful imports from other jobs/datasets remain committed. Do not delete the queue or reset all jobs to clear an alert. Inspect the JSON report and source archive, resolve the cause, and requeue individual held jobs with a reason.

## Deployment checklist

1. Review the patch and scheduling/monitoring proposal; take and verify a fresh production backup.
2. Ensure no old importer is active; pause its schedule if a scheduled run could overlap rollout. Apply `filings.0015_ingestion_reliability` (three new operational tables) and `rega.0003_add_report_and_withdrawal_forms` (form choices; no historical row updates).
3. Deploy matching web/cron code, configure the independent monitor service, and verify its failure notification path. Run a bounded ingestion pass, inspect counts, unresolved work and source hashes, then enable the proposed schedule.
4. Verify existing URLs, reviewed issuer fields, source XML, representative new report/withdrawal pages, exports and SEO. Confirm monitor freshness after completion.

Rollback: stop the new cron first, retain the additive tables and source evidence, and restore the prior code/schedule only after review. Do not drop provenance or restore a whole database over unrelated subsequent activity. Previously imported filing records retain their existing routes.

## Validation results

- **178 tests passed on PostgreSQL** against the final isolated release patch; no skips. Includes atomic attempt accounting, co-issuer discovery and a read-free notification probe.
- **178 tests passed on PostgreSQL** in the shared working tree, including the unrelated local growth tests; no skips.
- **178 tests completed on SQLite:** 166 passed and 12 PostgreSQL-specific concurrency tests skipped. Those concurrency tests all passed on PostgreSQL.
- The full migration chain succeeded from scratch. No migration-state drift in the changed filings/Reg A apps. Generated SQL creates operational tables/indexes only; the form-choice migration is a database no-op.
- No templates, styles, routes, SEO implementation files or production records were changed by this patch. Unrelated local signup/growth edits are excluded from the isolated review patch.
- `git diff --check` passes for tracked implementation changes. Original SEC text fixtures intentionally retain the source's trailing tabs/spaces; they are checksum-verified rather than reformatted.

## Evidence

Full PostgreSQL and SQLite logs, a patch against production release `f5765c45dca42e88b3010e92fb62fd71ff4bedfa`, migration SQL and real-source verification are in `outputs/pipeline-reliability/`. Original SEC regression fixtures are retained under `filings/tests/fixtures/sec_ingestion/` with source URLs and hashes.

A real October 21, 2026 daily index parsed successfully: 259 Form D entries, 8 crowdfunding entries and 17 Reg A entries. Original SEC `1-A-W` and `1-U` submissions passed conservative metadata extraction without inferring financial values. The tests cover retries, backoff, crash recovery, concurrent claims, fencing, atomic rollback, repeated ingestion, historical source/URL preservation, missing indexes, calendar closures, malformed/oversized sources and failure reporting, alongside the existing application regressions.

SEC references: [index publication and fair access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data), [official closure calendar](https://www.sec.gov/submit-filings/filer-support-resources/edgar-calendar), [Reg A submission types in the filer manual](https://www.sec.gov/files/edgar/filermanual/edgarfm-vol2-v78.pdf).

## Regressions fixed during release review

- Attempt counting now commits atomically with the job claim, including crash recovery.
- Failed HTTP responses close their connections before retrying or raising.
- SEC co-issuer index rows are grouped by accession with every observed candidate retained. Existing filings keep their issuer; new structured filings select only an index-listed primary CIK explicitly reported by the XML. A conflicting accession is held individually without blocking the rest of the index.

Fresh production backup and additive migrations were verified before deployment. The preflight recorded fingerprints for all existing filing rows, review records and issuer URLs, plus the 26 previously held field values (including the approved YM repair). Post-deployment evidence is retained in `outputs/pipeline-deployment/`.
