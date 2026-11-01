"""Public research pages; all data comes from existing local storage."""
import re

from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from config.metadata import metadata
from content.models import Article
from content.market_research import MARKET_RESEARCH
from .industry import SLUG_TO_NAME
from .intelligence import activity_report, filing_changes, percent
from .models import Issuer
from .research import directory_data

REPORTS = {
    "filing-activity": ("Monthly Form D filing activity", "Compare original notices, amendments, and distinct issuers across twelve months of stored SEC disclosures."),
    "amendments": ("Form D amendments and disclosure coverage", "Measure the amendment share of stored Form D filings and inspect missing financial fields without double counting reported sales."),
}


def hub(request):
    report = activity_report()
    if not report["stats"]["filings"]:
        request.seo_noindex = True
    return render(request, "research/hub.html", {
        "report": report, "canonical_path": "/research/", "research_page": "Research",
        "research_notes": Article.objects.filter(slug__in=[a['slug'] for a in MARKET_RESEARCH], published_at__lte=timezone.now()).exclude(body='').only('slug', 'title', 'meta_description', 'published_at'),
        **metadata("SEC private placement research", "Analyze stored SEC Form D activity, compare states and industries, and inspect changes between issuer disclosures with transparent calculations."),
    })


def report_detail(request, slug):
    if slug not in REPORTS:
        raise Http404
    title, description = REPORTS[slug]
    report = activity_report()
    if not report["stats"]["filings"]:
        request.seo_noindex = True
    return render(request, "research/report.html", {
        "report": report, "report_slug": slug, "report_heading": title,
        "research_page": title, "canonical_path": f"/research/{slug}/",
        **metadata(title, description),
    })


def compare(request):
    request.seo_noindex = True
    kind = request.GET.get("kind", "state")
    errors = []
    if kind not in {"state", "industry"}:
        errors.append("Choose state or industry comparisons.")
        kind = "state"
    directories = directory_data()
    options = [(r["code"], r["name"]) for r in directories["states"]] if kind == "state" else [
        (r["slug"], r["name"]) for r in directories["industries"]]
    valid = dict(options)
    left = request.GET.get("left", options[0][0] if options else "")
    right = request.GET.get("right", next((value for value, _ in options if value != left), ""))
    comparisons = []
    if len(options) >= 2:
        if left not in valid or right not in valid:
            errors.append("Choose two populated categories from the lists.")
        elif left == right:
            errors.append("Choose two different categories.")
        elif not errors:
            overall = activity_report()
            for value in [left, right]:
                report = activity_report(**({"state": value} if kind == "state" else {"industry": SLUG_TO_NAME[value]}))
                comparisons.append(dict(
                    name=valid[value], report=report,
                    share=percent(report["current"]["filings"], overall["current"]["filings"]),
                    url=f"/state/{value}/" if kind == "state" else f"/industry/{value}/",
                ))
    return render(request, "research/compare.html", {
        "kind": kind, "options": options, "left": left, "right": right,
        "errors": errors, "comparisons": comparisons,
        "comparison_months": [dict(month=a["month"], partial=a["partial"], left=a["filings"], right=b["filings"])
                              for a, b in zip(comparisons[0]["report"]["months"], comparisons[1]["report"]["months"])] if len(comparisons) == 2 else [],
        "canonical_path": "/research/compare/", "research_page": "Compare categories",
        **metadata("Compare Form D states and industries", "Compare monthly filing activity, amendment shares and issuer counts using reproducible categories from the stored dataset."),
    }, status=400 if errors else 200)


def changes(request):
    request.seo_noindex = True
    cik = request.GET.get("cik", "").strip()
    errors, issuer, records, comparison = [], None, [], None
    if cik:
        if not re.fullmatch(r"[0-9]{1,10}", cik):
            errors.append("Enter a numeric issuer CIK of up to ten digits.")
        else:
            issuer = get_object_or_404(Issuer, cik=cik)
            records = list(issuer.filings.only(
                "issuer_id", "accession_number", "filing_date", "form_type", "is_amendment",
                "total_offering_amount", "total_amount_sold", "num_investors", "minimum_investment",
            ).order_by("-filing_date", "-accession_number")[:200])
            by_accession = {f.accession_number: f for f in records}
            earlier = request.GET.get("earlier", records[1].accession_number if len(records) > 1 else "")
            later = request.GET.get("later", records[0].accession_number if records else "")
            if len(records) > 1:
                if earlier not in by_accession or later not in by_accession:
                    errors.append("Choose filings from this issuer's displayed history.")
                else:
                    try:
                        comparison = filing_changes(by_accession[earlier], by_accession[later])
                    except ValueError as exc:
                        errors.append(str(exc))
    return render(request, "research/changes.html", {
        "cik": cik, "change_issuer": issuer, "records": records, "comparison": comparison,
        "earlier_selected": request.GET.get("earlier", records[1].accession_number if len(records) > 1 else ""),
        "later_selected": request.GET.get("later", records[0].accession_number if records else ""),
        "errors": errors, "canonical_path": "/research/filing-changes/", "research_page": "Filing change viewer",
        **metadata("Compare issuer filing disclosures", "Inspect differences in reported offering amounts, amounts sold and investor counts between two SEC disclosures for the same issuer CIK."),
    }, status=400 if errors else 200)
