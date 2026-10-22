# Page titles and descriptions

## Audit and scope

The base template already renders HTML, Open Graph, and Twitter metadata from
`page_title` and `meta_description`. Most public templates inherit those values;
visible headings use their own text. The changes keep that separation and retain
the Form D Explorer brand.

The audit found vague search titles, state abbreviations without names, short or
overstated summaries, duplicate titles for same-name firms and same-day filings,
and guide descriptions that characterized exempt offerings as registrations.
The guide list was titled only "About" and articles without descriptions repeated
their title as their description.

Coverage includes the homepage, Form D search, recent filings, issuer and filing
details, related-person pages, industries, states, Form ADV adviser search and
details, Form C search and details, Regulation A search and details, the guide
index and ten built-in guides, API documentation, pricing, privacy, and terms.

## Formatting and accuracy

- `config/metadata.py` normalizes whitespace and adds one brand suffix. Django
  autoescaping remains enabled. Long firm names are shortened independently of
  identifiers; CIKs, CRDs, accession numbers, and filing dates remain intact.
- Issuer CIKs and adviser CRDs distinguish firms with the same name. Accession
  numbers distinguish filings from the same issuer, form type, and date. These
  detail titles can exceed typical search display widths intentionally; cutting
  the complete title would remove the distinguishing identifier.
- Paginated collections use the resolved page number in both tags. Filters keep
  stable collection metadata rather than echoing arbitrary user queries.
- Offering amounts are not described as amounts raised. Amendments, annual
  reports, withdrawals, and termination reports are described as filing records,
  not fresh fundraising or currently available investment opportunities.
- Adviser metadata does not assert that name-matched issuers are verified
  affiliations. Related-person metadata describes records listing a name, not a
  verified identity or exhaustive history.
- `content/metadata.py` contains curated titles and summaries for built-in guide
  slugs. This updates existing pages without reseeding article bodies or dates.
  Other articles use their authored metadata, with a plain-text body excerpt
  when the description is blank. Article JSON-LD uses the same description.
- Navigation, visible headings, article bodies, fees, data queries, canonical
  URLs, robots directives, and database schema are unchanged.

Example titles:

| Page | Title |
| --- | --- |
| Home | SEC Form D Filings & Private Placement Database \| Form D Explorer |
| Search | Search SEC Form D Filings \| Form D Explorer |
| California | California SEC Form D Filings \| Form D Explorer |
| Advisers | Investment Adviser Search — Form ADV \| Form D Explorer |
| Guide | What Is SEC Form D? Regulation D Guide \| Form D Explorer |

Google may select different titles and snippets. References:
[title links](https://developers.google.com/search/docs/appearance/title-link)
and [descriptions](https://developers.google.com/search/docs/appearance/snippet).

## Verification and release

Run `python manage.py check` and `python manage.py test --noinput`. The metadata
tests render complete pages, parse HTML tags, and check uniqueness, escaping,
social consistency, guide fallbacks, JSON-LD, all supported filing form types,
pagination, and HTMX partials. Local validation uses an isolated SQLite test
database; it does not query or change production data.

Validation after reconciliation: all 56 Django tests passed, including 13 metadata
tests and 16 technical SEO tests; Django's system check passed. A harmless warning
notes that collected production static files are absent in the test checkout.

The technical SEO foundation from PR #2 is integrated. `config/metadata.py`
alone formats page numbers; `config/seo.py` handles collection canonical URLs
and noindex rules. The shared structured-data tag uses the resolved description
and emits a single JSON-LD graph. Invalid collection page numbers return 404;
the tests now enforce that policy along with exactly one page-number label.
Form D search remains `noindex` but is crawlable in robots.txt so crawlers can
read that directive. See `docs/seo.md` for the complete indexing policy.

At the reconciliation audit, Railway's `web` service in `loyal-warmth` followed
`main` and was queued behind a Railway platform outage. Production settings were
verified in the dashboard: `DEBUG=False`, `SEO_INDEXING_ENABLED=True`,
`SITE_URL=https://formdexplorer.com`, both aliases configured, and
`ADSENSE_ENABLED=False`. Advertising therefore remains disabled when the older
advertising code ships with the SEO changes. No new migrations are introduced;
the migration dry run still reports the previously documented ID/index drift.
After release, verify Railway's deployed commit and inspect the live HTML metadata
on the homepage, one listing, one issuer, one filing, and one guide.
