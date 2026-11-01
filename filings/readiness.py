"""Read-only publication checks; a local audit cannot certify Google approval."""
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.db.models import Count
from django.db.models.functions import Trim
from django.utils import timezone

from config.advertising import cmp_url, publisher_id
from content.models import Article
from content.reviewed_guides import ARTICLES
from content.research_guides import RESEARCH_GUIDES
from content.market_research import MARKET_RESEARCH
from .intelligence import activity_report
from .models import Filing, Issuer


def quality_audit():
    report = activity_report()
    missing = []
    outdated = []
    for guide in ARTICLES + RESEARCH_GUIDES + MARKET_RESEARCH:
        article = Article.objects.filter(slug=guide["slug"]).first()
        if not article or not article.is_published or not article.body.strip():
            missing.append(guide["slug"])
        elif article.body != guide["body"]:
            outdated.append(guide["slug"])
    return {
        "scope": "Stored records and local configuration only; not an AdSense account or legal compliance certification.",
        "calculated_at": timezone.now().isoformat(),
        "eligible_form_d_records": report["stats"]["filings"],
        "eligible_issuer_ciks": report["stats"]["issuers"],
        "latest_filing_date": report["stats"]["latest"].isoformat() if report["stats"]["latest"] else None,
        "excluded_blank_issuer_records": Filing.objects.alias(issuer_name=Trim("issuer__name")).filter(issuer_name="").count(),
        "future_dated_records": Filing.objects.filter(filing_date__gt=timezone.localdate()).count(),
        "issuers_without_form_d": Issuer.objects.annotate(filing_count=Count("filings")).filter(filing_count=0).count(),
        "empty_published_articles": Article.objects.filter(published_at__lte=timezone.now()).alias(content=Trim("body")).filter(content="").count(),
        "missing_or_unpublished_guides": missing,
        "guides_differing_from_reviewed_source": outdated,
        "routes": [
            {"family": "Research reports", "classification": "retain when populated; noindex and omit from sitemap when empty"},
            {"family": "Issuer profiles", "classification": "enrich with source-linked disclosure comparisons; noindex empty Form D collections"},
            {"family": "State and industry", "classification": "retain populated directories; enrich page one; preserve sparse records without fabricated analysis"},
            {"family": "Search, filters, comparison tools, person names", "classification": "useful research utilities; noindex while allowing crawlers to read directives"},
            {"family": "Guides", "classification": "retain and correct; empty guides noindex and omitted from sitemap"},
            {"family": "ADV, C and Regulation A", "classification": "preserve source-based research and established access controls"},
            {"family": "Accounts, alerts, exports, API and billing", "classification": "preserve private/commercial workflows and existing noindex rules"},
        ],
    }


def readiness_audit():
    parsed = urlsplit(settings.SITE_URL)
    checks = []

    def check(name, status, detail):
        checks.append(dict(check=name, status=status, detail=detail))

    check("Canonical production origin", "pass" if parsed.scheme == "https" and parsed.hostname == "formdexplorer.com" else "action", "Production must use SITE_URL=https://formdexplorer.com; local origins are expected during development.")
    check("Indexing enabled", "pass" if settings.SEO_INDEXING_ENABLED else "action", "Enable only on the canonical production environment.")
    check("Publisher verification identifier", "pass" if publisher_id() else "action", "A syntactically valid account-provided ID enables the meta tag and ads.txt; syntactic validity does not prove account ownership.")
    if settings.ADSENSE_ENABLED:
        ready = bool(settings.ADSENSE_CMP_READY and cmp_url() and publisher_id())
        check("Advertising configuration", "pass" if ready else "action", "Serving requires real account approval, matching units and verified regional consent; unknown consent fails closed.")
        article_slot = bool(re.fullmatch(r"[0-9]{10}", settings.ADSENSE_ARTICLE_SLOT_ID))
        guide_slot = settings.ADSENSE_GUIDES_SLOT_ID
        check("Manual display units", "pass" if article_slot and (not guide_slot or re.fullmatch(r"[0-9]{10}", guide_slot)) else "action", "Use actual matching ten-digit units; the guide-list unit is optional. Identifier format cannot verify ownership or inventory approval.")
    else:
        check("Advertising configuration", "pass", "Ad serving is disabled. Verification works independently; no ads are needed on research utilities.")
    check("Real account and consent validation", "manual", "Owner must check domain status, actual publisher identity, account policy issues, Auto ads disabled, real regional CMP behavior, privacy wording and manual review submission. Local checks cannot verify these.")
    quality = quality_audit()
    check("Research data", "pass" if quality["eligible_form_d_records"] else "action", "At least one eligible record is required to publish indexable computed reports; inspect production coverage and import health.")
    check("Guide deployment", "action" if quality["missing_or_unpublished_guides"] or quality["guides_differing_from_reviewed_source"] else "pass", "Compare seeded article bodies with reviewed source; apply the existing seed_articles release step after editorial review.")
    check("Live deployment", "manual", "Verify public response codes, canonical domain, crawler access, ads.txt, mobile rendering, Search Console and production account/export workflows after the tested release.")
    return dict(assessment="LOCAL_CHECKS_ONLY", checks=checks, quality=quality)
