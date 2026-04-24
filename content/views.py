import markdown as md
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils.safestring import mark_safe

from .models import Article


def article_list(request):
    articles = Article.objects.exclude(published_at__isnull=True).order_by("-published_at")
    ctx = {
        "articles": articles,
        "page_title": "About — Form D Explorer",
        "meta_description": (
            "Form D Explorer is a clean, fast search interface over SEC Form D filings. "
            "Free issuer lookup; paid plans for CSV export, alerts, and API access."
        ),
        "canonical_path": "/learn/",
    }
    return render(request, "content/article_list.html", ctx)


def article_detail(request, slug: str):
    if slug == "api":
        return api_docs(request)
    article = get_object_or_404(Article, slug=slug, published_at__isnull=False)
    body_html = mark_safe(md.markdown(article.body, extensions=["extra", "toc"]))
    ctx = {
        "article": article,
        "body_html": body_html,
        "page_title": f"{article.title} | Form D Explorer",
        "meta_description": article.meta_description or article.title,
        "canonical_path": f"/learn/{article.slug}/",
    }
    return render(request, "content/article_detail.html", ctx)


def api_docs(request):
    ctx = {
        "page_title": "API reference | Form D Explorer",
        "meta_description": (
            "REST API reference for Form D Explorer. Endpoints, authentication, "
            "rate limits, and response formats."
        ),
        "canonical_path": "/learn/api/",
    }
    return render(request, "content/api_docs.html", ctx)
