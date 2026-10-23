# C3 historical identity and withdrawal review

The reviewed repair keeps CIK 1827424 (historical C3 Capital, Inc.) separate from CIK 1981779 (C3 Bullion, Inc.). The original filing accessions, issuer associations, form types, financial values, source fields and URL slugs are preserved. The reviewed evidence and exact payload are in `filings/tests/fixtures/c3_review.json`.

`IssuerIdentityReview` supplies the historical-name explanation and original SEC source receipts. Reviewed issuers retain their identity columns during ingestion; incoming parsed identities are recorded in `IssuerIdentityObservation`, with an accession, date and deduplication fingerprint. The issuer row lock serializes ingestion with repair application.

`RegAFilingReview` records a source-reported withdrawal event against one accession and CIK. It does not replace the original form type, merge offerings, or infer an issuer-wide withdrawal. The two events target 0001827424-23-000007 / 024-12366 and 0001981779-24-000001 / 024-12387. The separate 024-12367 offering is not marked withdrawn. Status and identity context appear on relevant pages, search results and appended Excel export columns. Existing numeric export columns keep their values and order.

## Operations

Apply only after a fresh backup and validation of the original review manifest, source hashes, exact issuer/filing snapshots, held fields and global fingerprints. Migrate the additive tables, deploy compatible web and ingestion code, and then commit both name fields plus all three review records atomically using `apply_c3_review`. The reviewed historical name must not be applied without its explanatory records and compatible UI. Repeated application or any before-value/source/URL drift fails closed.

Rollback requires a separately checked transaction: verify current values and review rows match this release, account for any later observations, restore only the two reviewed before-values, and remove the corresponding review records together. Never delete or reassign original filings. Additive tables may remain in place. Do not blindly roll back to code that omits the notices while retaining the historical-name repair.

## Validation

The PostgreSQL suite covers atomic rollback, concurrent duplicate application, ingestion racing with repair, source drift, original values and URLs, rendered context, and paid export context/access control. SQL migration output creates only supplemental tables/indexes. Production verification must compare all original filing fingerprints, all issuer URLs, protected identity fields, both C3 snapshots, and the exact review records. No live Stripe operation is involved.
