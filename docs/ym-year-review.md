# Reviewed YM incorporation year

YM Corp (CIK 1416299) has conflicting source years: its September 2026 Form D disclosures report 2025, while its original registration statement and 2026 offering circular establish incorporation in 2006. The 2025 exhibits document revival/name amendments. Only the shared issuer year is corrected; source XML, filings, URL components and all other issuer columns remain untouched.

`IssuerFieldReview` protects the year under the same issuer row lock used by all three ingestion pipelines. `IssuerFieldObservation` retains each incoming value, including blank and conflicting values, with accession/date provenance. The four older metadata-only YM filings retain their empty XML without invented observations; the two XML-backed Form D years are recorded. Other identity fields keep their existing update rules. The existing C3 identity guard remains unchanged.

Filing detail pages label the year as reviewed issuer data and link original SEC evidence. The issuer page shows the same note. API issuer payloads add `field_reviews` only for reviewed issuers; the existing year field retains its type. No routes or canonical metadata change.

Application uses `apply_ym_year_review` after a fresh verified backup, exact issuer/source snapshot checks, the additive migration, and successful web/cron deployments. The operation rejects drift/repeats and commits the year, provenance and original Form D observations atomically. A whole-identity C3 lock is deliberately not attached to YM.

Validation: 141 PostgreSQL tests passed, including two-operator races, ingestion before/after review, rollback, source preservation, field-specific updates, pages, API provenance, and existing C3 behavior. New app migrations have no drift. Whole-project migration autodetection still reports the same unrelated advisers/content/crowdfunding drift as the unchanged production baseline; no unrelated migrations are included.

Rollback: retain the additive tables and provenance. If a data rollback is approved, restore the original year and remove its review/observations in one issuer-locked transaction after revalidating drift; never restore a whole database snapshot over unrelated subsequent activity without explicit review. Do not revert to an importer that ignores the field review while the corrected year is active.
