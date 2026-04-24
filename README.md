# Form D Explorer

Clean, fast search over SEC Form D filings. Django 5 + HTMX + Postgres.

## Local dev

Requires Python 3.12+ and Postgres (optional; SQLite works for scaffolding except for the `pg_trgm` index).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # edit DATABASE_URL for local Postgres
```

### Tailwind (standalone CLI — no Node required)

Download the [Tailwind standalone CLI](https://github.com/tailwindlabs/tailwindcss/releases/latest) binary for your OS, chmod +x, and drop it at `./tailwindcss`.

```bash
./tailwindcss -i static/src/input.css -o static/css/app.css --minify        # one-shot
./tailwindcss -i static/src/input.css -o static/css/app.css --watch         # dev
```

The `@tailwindcss/typography` plugin is required; install it via `npm i -D @tailwindcss/typography` once (even with the standalone CLI, typography needs Node — or drop the plugin if you don't want it and remove `prose` classes from `templates/content/article_detail.html`).

### Migrate + run

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Seed filings

```bash
python manage.py ingest_form_d --days 7                 # last 7 days
python manage.py ingest_form_d --start 2026-04-14 --end 2026-04-20
```

Idempotent — safe to re-run. Upserts on `accession_number`.

## Deploy: Railway

1. Create a Railway project, provision the Postgres plugin.
2. Connect this repo. Railway uses the `Procfile` (release: migrate + collectstatic; web: gunicorn).
3. Set env vars:
   - `SECRET_KEY`
   - `DEBUG=False`
   - `ALLOWED_HOSTS=your-domain.com,your-app.up.railway.app`
   - `DATABASE_URL` (auto-injected by the Postgres plugin)
   - `SITE_URL=https://your-domain.com`
   - `EDGAR_USER_AGENT=Form D Explorer luke@dawncrestconsulting.com`
4. Add a cron service in Railway running daily:
   ```
   python manage.py ingest_form_d --days 2
   ```
   (two days handles late-arriving filings.)

## Stripe (Phase 2)

1. Create products + prices in Stripe dashboard: Pro Monthly ($19), One-time Export ($15), API Monthly ($49).
2. Copy the `price_xxx` IDs into `.env` as `STRIPE_PRICE_PRO_MONTHLY`, `STRIPE_PRICE_ONE_TIME_EXPORT`, `STRIPE_PRICE_API_MONTHLY`.
3. Add a webhook endpoint in Stripe pointing to `https://<your-domain>/stripe/webhook/`. Copy the signing secret into `DJSTRIPE_WEBHOOK_SECRET`.
4. Required events: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `customer.subscription.resumed`, `customer.subscription.paused`, `invoice.payment_failed`.

Test locally with the Stripe CLI:

```bash
stripe listen --forward-to localhost:8000/stripe/webhook/
```

## Email alerts (Phase 2)

SMTP (Postmark/SendGrid) configured via env (`EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`). In DEBUG, emails print to the console.

Daily cron (Railway):

```
python manage.py send_saved_search_alerts
```

## API (Phase 3)

REST, Bearer-token, 10k requests / 30 days per key. Requires the API Access subscription tier.

- `GET /api/v1/filings/` — list / search filings
- `GET /api/v1/filings/<accession>/` — filing detail
- `GET /api/v1/issuers/<cik>/` — issuer profile

Docs: `/learn/api/`. Keys managed at `/account/api-keys/`.

## AdSense (Phase 3)

Placeholder `<!-- ADSENSE SLOT -->` comments sit in `templates/content/article_list.html` and `templates/content/article_detail.html`. Drop the AdSense `<script>` + `<ins>` in at those locations after Google approves the site. Never add AdSense to utility pages (home, search, issuer, filing, industry, state, recent).

## Tests

```bash
python manage.py test
```

## Structure

- `config/` — Django project (settings, urls, wsgi)
- `accounts/` — custom User model (email as username)
- `filings/` — Issuer / Filing / RelatedPerson models, ingestion pipeline, public views, search
- `content/` — Article model for `/learn/` pages
- `templates/` — shared templates; all server-rendered, all have unique `<title>` + meta description

## Constraints

- Webapp NEVER hits EDGAR at request time. Reads Postgres only.
- Ingestion rate-limited to ~8 req/sec with a compliant User-Agent.
- No AdSense code in templates — placeholder `<!-- ADSENSE SLOT -->` comments only.
- AdSense never goes on utility pages (home, search, issuer, filing, industry, state, recent).
