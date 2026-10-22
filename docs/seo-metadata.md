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

Validation on this branch: all 40 Django tests passed, including 13 new metadata
tests; Django's system check and `git diff --check` passed. A harmless warning
notes that collected production static files are absent in the test checkout.

This change is independent of the concurrent crawl/indexing work. Reconcile
shared view/context/template edits when combining the branches, especially page
number formatting so it is applied only once. Form D search remains `noindex`
and disallowed by this branch's existing robots.txt; metadata does not itself
enable indexing.

At the release audit, Railway's `web` service in `loyal-warmth` followed `main`
but its latest successful deployment was `ed01040`. The branch base was
`280bbb9`, which also includes the separate advertising change. Review that
release gap before deploying `main`; this metadata change does not enable ads,
set Railway variables, or modify service configuration. After an authorized
release, verify Railway's deployed commit and inspect the live HTML metadata
on the homepage, one listing, one issuer, one filing, and one guide.
