from django.core.management.base import BaseCommand
from django.utils import timezone

from content.models import Article


ARTICLES = [
    {
        "slug": "what-is-form-d",
        "title": "What is SEC Form D? A plain-English guide",
        "meta_description": (
            "Form D is the disclosure a company files with the SEC after selling "
            "unregistered securities under Regulation D. What it says, why it matters, "
            "and how to read one."
        ),
        "body": """\
## The short version

Form D is a notice an issuer files with the SEC after raising money under **Regulation D** —
the exemption that lets private companies sell securities without registering them publicly. It
is not a fundraising approval; it is a **report that the fundraising already happened** (or
started). The first Form D is due within 15 days of the first sale.

## Why Form D exists

Most public-company disclosure (S-1s, 10-Ks, 8-Ks) exists because the SEC wants investors to have
information before they buy. Regulation D offerings skip that registration, so instead of a
detailed prospectus, issuers file a short standardized form capturing:

- Who the issuer is (name, CIK, state of incorporation, address)
- The offering size (amount offered, amount sold so far)
- The exemption claimed (506(b), 506(c), 504, etc.)
- The date of first sale, minimum investment, number of investors
- Sales commissions and finders' fees paid
- The issuer's executive officers, directors, and promoters

It is public by design. Anyone can read it on EDGAR — or here.

## What Form D does *not* tell you

- **Nothing about financial performance.** No revenue, EBITDA, burn rate, or cap table.
- **No investor names.** Just a count of how many invested and the minimum investment.
- **No valuation.** You can back it out from total offered vs. stake in some cases, but the form
  itself doesn't disclose it.
- **It's self-reported.** The SEC does not audit Form Ds. Errors and stale amendments are common.

## D vs. D/A

A plain **D** is the original filing. A **D/A** is an amendment — issuers file these to update
the total sold, change the reported number of investors, extend an offering, or correct a
typo. Some issuers file D/As every quarter while a fund is still raising; others never amend.

## How to read one

A few fields that matter more than you'd think:

- **Total offering amount vs. amount sold.** "Up to $50M offered, $12M sold" tells you where a
  fund is in its raise — and if sold = $0, often the filing was triggered by a first commitment
  with no money yet in the door.
- **Date of first sale.** Starts the 15-day filing clock and signals when the deal actually
  began.
- **Industry group.** The issuer picks this from a fixed SEC list. "Pooled Investment Fund"
  covers most VC / PE / hedge fund vehicles.
- **Related persons.** Executive officers and directors, with city and state. Useful for
  deanonymizing pseudonymous issuer names.

## Looking things up

Every Form D filing since 2008 is on [SEC EDGAR](https://www.sec.gov/edgar). Form D Explorer
re-indexes them into a faster search UI with per-issuer pages, industry and state rollups,
and filters for offering size and date. Start at the [homepage](/) or browse the
[most recent filings](/recent/).
""",
    },
    {
        "slug": "reg-d-506b-vs-506c",
        "title": "Rule 506(b) vs. 506(c): which Reg D exemption is being used?",
        "meta_description": (
            "The two most common Regulation D exemptions are 506(b) and 506(c). They differ "
            "on general solicitation, accreditation verification, and investor pool — here's "
            "how to tell them apart on a Form D."
        ),
        "body": """\
## The headline difference

Both **Rule 506(b)** and **Rule 506(c)** let issuers raise unlimited capital from accredited
investors. The practical split:

- **506(b)**: no public advertising; up to 35 non-accredited investors allowed; issuer can
  rely on investor self-certification of accredited status.
- **506(c)**: public advertising *is* allowed; accredited investors only; issuer must take
  **reasonable steps to verify** accredited status (tax returns, W-2s, broker-dealer letter,
  etc.).

In short: **506(b) is quiet; 506(c) is loud but has a stricter door.**

## Why it shows up on Form D

Form D lists the exemption(s) claimed under "Federal Exemption(s) and Exclusion(s)". You'll see
codes like:

- `06b` → Rule 506(b)
- `06c` → Rule 506(c)
- `04` → Rule 504 (smaller, $10M cap)
- `3(c)(1)`, `3(c)(7)` → exemptions under the **Investment Company Act** for the fund itself
  (not the securities sale) — common on pooled-fund filings

A single filing can claim multiple. A venture fund raising under 506(b) that's structured as a
3(c)(1) fund will show both.

## What "general solicitation" means in practice

Under 506(b), the issuer must have a pre-existing, substantive relationship with every prospect.
In practice this means:

- A VC firm emailing its LP list: fine.
- A founder posting "we're raising a seed round" on LinkedIn with specific terms: not fine under
  506(b) — that's general solicitation and pushes the deal to 506(c).

Many Rule 506(b) issuers inadvertently violate this rule; the SEC occasionally enforces.

## What "reasonable verification" means under 506(c)

The SEC doesn't prescribe a single method, but they list non-exclusive safe harbors:

- Two most recent tax-return years showing income ≥ $200k individual / $300k joint
- A net-worth calculation based on bank/brokerage statements and a credit report
- A written confirmation from a licensed broker-dealer, investment adviser, attorney, or CPA

Most issuers outsource this step to third parties like VerifyInvestor, Parallel Markets, or
EarlyIQ.

## Reading it on a Form D

When you see `06b` alone with a high number of investors and "minimum investment $250,000", it's
almost certainly a traditional private fund. When you see `06c` with marketing-funnel-style
round numbers and a low minimum, you're probably looking at a syndicate or a crowdfunding-style
raise that wanted to advertise publicly.

## Looking up filings by exemption

Form D Explorer indexes the `offering_type` field (which stores the claimed exemptions). Browse
[pooled investment fund filings](/industry/pooled-investment-fund/) to see 506(b) + 3(c)(1)/(7)
stacks, or search for specific issuers on the [homepage](/).
""",
    },
    {
        "slug": "form-d-vs-form-d-a",
        "title": "Form D vs. Form D/A: what amendments actually mean",
        "meta_description": (
            "A Form D/A amends a prior Form D filing. Here's when issuers file one, "
            "what typically changes, and how to read a stack of amendments."
        ),
        "body": """\
## The mechanics

Every Form D filing starts as a **Form D** (original). Any later filing that updates or
corrects it is a **Form D/A** (amendment). Both live under the same filing family — you can spot
them in a search because they share the issuer CIK and usually fall close in time.

## When is an amendment required vs. optional?

The SEC requires a Form D/A:

- **Annually** while the offering is still ongoing (i.e. the issuer is still raising) — within
  one year of the most recent filing.
- To **correct a material mistake** in a previously filed Form D.
- To **reflect a change in certain key facts** — issuer name, offering amount, or the number of
  investors once sales close.

Amendments are optional for non-material updates. Some issuers amend aggressively, some almost
never.

## What typically changes between D and D/A

Stack a D and its D/A side by side and you'll usually see one of these:

- **Total amount sold goes up.** Initial D says "up to $50M offered, $10M sold"; six months
  later the D/A says "$28M sold". Classic pattern for a fund actively raising.
- **Number of investors goes up.** Same story: raise progresses, more LPs commit.
- **Offering amount increases.** Less common, but an issuer who under-estimated target size
  will file a D/A to reflect it.
- **Issuer name or address correction.** Typos, entity-name changes, office moves.
- **Related persons list changes.** New director, officer departure, new promoter.

## What doesn't change

The **accession number** — each filing gets its own unique accession — but the **CIK** is the
same across all filings from the same issuer. Form D Explorer groups them by CIK on
[per-issuer pages](/) so you can see the full sequence.

## Reading an amendment stack

The useful signal is *velocity*:

- **Many D/As in a short window** → active fundraise, often approaching close.
- **One D, then a D/A a year later** → required annual update; no inference about deal health.
- **D, then D/A within days** → typo fix; ignore.
- **D from 2019, no D/As** → offering either closed or the issuer is non-compliant with the
  annual-amendment rule (surprisingly common).

## Where to see them

The per-issuer page on Form D Explorer lists every filing (D and D/A) chronologically, each
linking to its detail view with the full offering parameters, related persons, and a link back
to the original SEC EDGAR record.
""",
    },
    {
        "slug": "how-to-read-a-form-d",
        "title": "How to read a Form D: a field-by-field walkthrough",
        "meta_description": (
            "A practical field-by-field guide to reading a Form D filing — what each "
            "section tells you, what to ignore, and what signals matter."
        ),
        "body": """\
Form D is short, but every field carries signal if you know what to look for. This walkthrough
goes section by section on a typical filing.

## 1. Header

- **Submission Type** — `D` or `D/A` (amendment). Always check — a D/A can look like a new
  filing but it's updating an earlier one.
- **Filing Date** — when it was submitted to the SEC. Not necessarily when the offering
  started.

## 2. Primary Issuer

The company actually raising money.

- **Entity Name** — legal name. Fund vehicles often read like "Acme Ventures Fund III LP".
- **CIK** — the SEC's central index key. **This is the canonical issuer identifier** — names
  change, CIKs don't.
- **Entity Type** — "Corporation", "Limited Partnership", "LLC", etc.
- **Jurisdiction of Inc.** — where the legal entity is organized (often Delaware regardless of
  where the business operates).
- **Year of Incorporation** — useful for distinguishing same-named vehicles.
- **Address + Phone** — street address. For funds this is usually the GP's office, not the
  portfolio.

## 3. Related Persons

Executive officers, directors, and promoters (promoters are rare).

Each entry: name, relationship, city, state. **This is the deanonymization field** — an issuer
named "SPV Series 2024-B LLC" with "John Smith, Executive Officer" is often a single-purpose
vehicle for a named principal's deal.

## 4. Industry Group

A fixed SEC enum. Most common on the site:

- **Pooled Investment Fund** — VC, PE, hedge funds, most fund-of-funds
- **Other Technology**, **Biotechnology**, **Pharmaceuticals** — operating companies by sector
- **Real Estate**, **REITS and Finance** — real-asset vehicles
- **Commercial Banking**, **Insurance** — financial institution raises

## 5. Issuer Size (optional, rarely populated)

Revenue and net-asset-value buckets. Usually blank on fund filings.

## 6. Federal Exemptions and Exclusions

The critical section. Codes you'll see:

- `06b` / `06c` — Rule 506(b) vs. 506(c). See
  [the 506(b) vs. 506(c) guide](/learn/reg-d-506b-vs-506c/).
- `04` — Rule 504 ($10M cap).
- `3(c)(1)` / `3(c)(7)` — Investment Company Act exemptions.

## 7. Type of Filing

- **New notice** or **amendment**
- **Date of First Sale** — the clock for the 15-day filing requirement.
- **More than one year** — whether the offering will run longer than a year.

## 8. Offering Sales Amounts

- **Total Offering Amount** — the ceiling. Sometimes "indefinite" on open-ended funds.
- **Total Amount Sold** — actual dollars raised so far.
- **Total Remaining to Be Sold** — math.

**Read together**, these two tell you where a raise is. Total sold = $0 is common on a fresh D
(first sale triggered the filing obligation, money hasn't cleared yet).

## 9. Minimum Investment

The smallest accepted check size. $250,000 is a classic private-fund default.

## 10. Sales Commissions and Finders' Fees

Paid to placement agents and brokers. Many direct-raised deals report $0.

## 11. Use of Proceeds (fraction to officers/directors)

Percentage of the raise paid to related persons. High values (>5%) warrant attention.

## 12. Signature

The person signing attests accuracy under SEC rules. Not a guarantee of anything — see the
caveats in [our Form D primer](/learn/what-is-form-d/).

## Putting it together

A typical $100M venture fund Form D: entity type "Limited Partnership", Delaware jurisdiction,
"Pooled Investment Fund" industry, `06b` + `3(c)(1)` exemptions, $250k minimum, a single
executive officer listed (the GP), $0 sales commissions. A crowdfunded syndicate will look
very different: `06c` exemption, $1k or $10k minimum, 50+ investors on the first filing.

Once you've read a dozen, the patterns are obvious at a glance.
""",
    },
]


class Command(BaseCommand):
    help = "Seed or update /learn/ articles (idempotent)."

    def handle(self, *args, **opts):
        now = timezone.now()
        for data in ARTICLES:
            article, created = Article.objects.update_or_create(
                slug=data["slug"],
                defaults={
                    "title": data["title"],
                    "meta_description": data["meta_description"],
                    "body": data["body"],
                    "published_at": now,
                },
            )
            self.stdout.write(
                self.style.SUCCESS(f"{'created' if created else 'updated'}: {article.slug}")
            )
