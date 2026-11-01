from django.shortcuts import render

from config.metadata import metadata
from filings.intelligence import activity_report


def about(request):
    return render(request, "content/about.html", {
        "canonical_path": "/about/",
        **metadata("About the publisher and contact", "Form D Explorer is built and maintained by Dawn Crest Consulting. Learn about its purpose, SEC data sources, research limitations and data-correction contact."),
    })


def editorial(request):
    return render(request, "content/editorial.html", {
        "canonical_path": "/editorial/",
        **metadata("Editorial standards and corrections", "Read Form D Explorer's standards for source attribution, financial calculations, human review, corrections and separation of research from advertising."),
    })


def coverage(request):
    return render(request, "research/coverage.html", {
        "report": activity_report(), "canonical_path": "/research/coverage/",
        "research_page": "Coverage",
        **metadata("SEC dataset coverage and field availability", "Inspect the available Form D date range, distinct issuer count, filing freshness and missing numeric disclosures. Understand what the stored dataset can establish."),
    })
