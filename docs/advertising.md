# Advertising setup and release guide

## Recommendation

Start with manual Google AdSense display units on editorial content, alongside the existing paid exports. One horizontal responsive unit sits after each guide; an optional second unit ID serves the bottom of the About/guides listing. There is no in-article interruption, sticky ad, overlay ad, or ad beside a search form. Signed-in paid users and staff are excluded. Keep Auto ads, anchor ads, vignette ads, and automated placement experiments OFF in AdSense; remote Auto ads could otherwise override this layout on editorial pages.

AdSense approval and revenue are not guaranteed. The site's original educational articles are the strongest initial inventory. Do not add placements to search results or other utility screens just to increase impressions. Evaluate actual editorial traffic and revenue before expanding; direct sponsorship can be considered later if this specialist audience is too small for useful display revenue.

## Verified deployment (October 21, 2026)

- Repository: https://github.com/Luketheprogram/formdexplorer, default branch `main`.
- Django 5, server-rendered templates, HTMX, PostgreSQL, WhiteNoise, Gunicorn, Tailwind, Stripe/dj-stripe. This change adds no runtime package or database migration.
- Railway workspace **FormDExplorer**, project **loyal-warmth** (`94b00042-a033-4c97-81e9-232859b3afa9`), environment **production** (`47382bf3-275b-4821-b000-8a47a580980f`).
- Web service **web** (`0a41d75c-1a1e-44f8-b741-6bd7f2900096`) follows `main` and serves `formdexplorer.com`, `www.formdexplorer.com`, and `web-production-04137.up.railway.app`.
- Latest observed web deployment: SUCCESS, commit `ed0104057f804c3930399ceb9fe5a3d8cbdc6c11`, deployed August 3, 2026. No staged Railway changes were present. No advertising variable names were present.
- Railway dashboard reports Railpack; `railway.json` selects Nixpacks, and `nixpacks.toml` builds Tailwind and collects static files. Confirm the effective builder from the next build logs and verify the new JS/CSS are collected. Do not silently change builders.
- The project also has ingestion and database services. Advertising configuration belongs on **web** only. No Railway configuration was changed during implementation.

## 1. Verify the existing AdSense account

On October 21, 2026, the existing AdMob-linked publisher account was extended to website AdSense and `formdexplorer.com` was added. Google shows **Requires review**; ownership verification and review submission remain pending. The verified public publisher ID is `ca-pub-1796408580720090`. Google reports that it already has the payment information. No new payment or identity information was submitted. Complete any further identity, phone, or address checks Google requests directly in the account.

The exact proposed web-service settings are in [adsense-verification.env](adsense-verification.env). They have not been applied to Railway. Meta-tag verification is selected in AdSense; do not check “I've placed the HTML meta tag” until the authorized deployment is confirmed live.

Copy the public publisher ID, `ca-pub-` followed by 16 digits. Set only `ADSENSE_CLIENT_ID` on the web service for the initial verification release. Keep both enablement flags false. This adds a `google-adsense-account` meta tag and serves the corresponding seller record at `/ads.txt`; no Google advertising script is loaded. No guessed account identifiers are shipped.

After an authorized deployment, check the live homepage source and `https://formdexplorer.com/ads.txt`, then choose the **Meta tag** verification method in AdSense, click **Verify**, and **Request review**. Google supports this method without its advertising script on the homepage. DNS changes are not normally required for this verification method. If Search Console separately asks for DNS ownership verification, use only its exact account-provided TXT value.

References: [Connect your site](https://support.google.com/adsense/answer/7584263?hl=en), [ads.txt](https://support.google.com/adsense/answer/12171612?hl=en).

## 2. Configure Google's certified consent platform

In AdSense **Privacy & messaging**, publish European regulations and applicable US state privacy messages for the domain. Include the privacy URL `https://formdexplorer.com/privacy/`, the actual operator details, and appropriate ad partners. Offer **Consent**, **Do not consent**, and **Manage options**. Keep Google's regional opt-out links enabled. Review the privacy text against actual operations before release, including the existing hosting, email, retention, and error-monitoring claims.

This implementation deliberately loads the consent platform separately from the advertising library. Copy the Google consent message tag's **script URL** from your account into `ADSENSE_CMP_SCRIPT_URL`. It must use HTTPS, the exact host `fundingchoicesmessages.google.com`, and path `/i/pub-<your publisher digits>`. Copy any query string exactly. This setting takes a URL, not HTML. If your account only supplies the combined AdSense loader, do not substitute that URL or enable ads: obtain and validate the standalone Google message tag or adapt the integration to another certified CMP. If the generated tag includes additional required bootstrap code, compare it with this loader before release. The standalone integration must be tested with the real account; synthetic tests cannot certify it.

The local “Allow advertising” choice is an additional opt-in, **not a certified CMP**. It does not replace Google's regional consent flow. This conservative launch:

- Makes no Google advertising/CMP request before local opt-in. Google Fonts/HTMX are pre-existing unrelated resources.
- Requires a successfully loaded TCF API: either an explicit non-applicability result or settled consent for Google (vendor 755) and device storage (purpose 1). Google consumes the full TCF string for other required purposes.
- Requires Google's initial US privacy status to be known and not opted out. Missing callbacks fail closed, even outside regulated regions.
- Requests non-personalized ads; these still require appropriate consent and may use cookies.
- Blocks advertising when Global Privacy Control is enabled.
- Stores the local choice for 180 days. Revocation reloads the document to stop loaded vendor scripts; it cannot delete third-party cookies or retract data already sent.
- Provides a footer opt-out on every page while configured. The Google consent settings button appears on eligible editorial pages once the CMP is ready. Subsequent US GPP section changes conservatively turn ads off and reload.

References: [Certified CMP requirements](https://support.google.com/adsense/answer/13554116?hl=en), [TCF integration](https://support.google.com/adsense/answer/9804260?hl=en), [Google Privacy & messaging API](https://developers.google.com/funding-choices/fc-api-docs).

## 3. Create manual units and set web variables

In AdSense, create responsive display ad units named, for example, `Guide footer` and `About footer`. Copy their numeric `data-ad-slot` values. The About unit is optional; leave it blank to monetize articles only.

| Variable | Value / purpose |
| --- | --- |
| `ADSENSE_CLIENT_ID` | Your actual `ca-pub-…` publisher ID; enables verification only |
| `ADSENSE_ARTICLE_SLOT_ID` | Actual 10-digit guide display unit ID |
| `ADSENSE_GUIDES_SLOT_ID` | Optional actual 10-digit About display unit ID |
| `ADSENSE_CMP_SCRIPT_URL` | Account-provided standalone Google message script URL |
| `ADSENSE_CMP_READY` | `False` until published messages and account-specific integration have been verified |
| `ADSENSE_ENABLED` | `False` until approval, release review, and live consent validation |

All settings default to blank/false. Invalid or incomplete settings suppress placements. Setting the public publisher ID alone cannot start advertising. Use the matching real account and units; do not put test IDs from automated tests into Railway.

## 4. Verify and release

Before production, run `python manage.py check`, `python manage.py test`, and `node --check static/js/advertising.js`. Build Tailwind and collect static files using the existing deployment build. For browser tests, install `@playwright/test` in a temporary directory, migrate/seed a local development database, and run `tests/advertising.browser.cjs` as described at its top. Browser tests intercept all external requests and simulate Google responses; they do not request real ads.

Review the code diff before pushing: Railway follows `main`, so a push/merge there can deploy immediately. Do not push to `main` or apply Railway variables without the owner's release authorization. Deploy verification first with ads disabled. Once Google marks the site ready, test the genuine CMP on an authorized staging domain with the correct account configuration; Google's URL previews `?fc=alwaysshow&fctype=gdpr` and `?fc=alwaysshow&fctype=ccpa` can help inspect published messages. Local opt-in is still needed before the CMP loads. Do not click live ads during testing.

Check fresh/returning users, allow/reject, preference withdrawal, GPC, blocked storage, blocked CMP/ad scripts, and mobile widths. Check EEA/UK/Swiss and US flows with actual regional signals; URL previews alone do not prove geo-detection. Ensure unknown, denied and opted-out cases send no ad request. Confirm the CMP APIs used here are returned in every enabled region before setting both flags true. If any callback is unavailable, ads stay off: resolve the integration rather than bypassing the gate.

After a release, confirm successful Railway deployment, both domain redirects/TLS, `ads.txt`, verification metadata, `/privacy/`, and the new static assets. Smoke-test search/HTMX, login, account, exports, and checkout. Verify paid accounts receive no placements. Monitor Google policy reports and browser errors. To stop advertising, set `ADSENSE_ENABLED=False` on web and deploy that change; existing open tabs finish their current page, but new loads have no advertising code.

## Validation limits

Local tests use SQLite and mocked Google responses. They cover application regressions, consent gates and responsive placement behavior, not PostgreSQL production performance, real ad fill, AdSense account approval, or certified consent-message delivery. Those final checks require the new account and an explicitly authorized release. No revenue estimate is defensible without traffic data.
