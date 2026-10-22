import markdown as md
from html import unescape
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.html import strip_tags
from django.utils.text import Truncator
from django.views.decorators.http import require_POST

from .models import Article, NewsletterSubscriber
from config.advertising import placement
from config.metadata import clean_text, metadata, short_name
from .metadata import GUIDES


def article_list(request):
    articles = Article.objects.exclude(published_at__isnull=True).order_by("-published_at")
    ctx = {
        "articles": articles,
        **metadata(
            "SEC Filing Guides: Form D, Form C, ADV & Reg A+",
            "Learn how to read SEC private market filings. Explore guides to Form D, "
            "Regulation D exemptions, crowdfunding, Reg A+ offerings, and investment advisers.",
        ),
        "canonical_path": "/learn/",
    }
    ctx.update(placement(request, "guides"))
    return render(request, "content/article_list.html", ctx)


def article_detail(request, slug: str):
    if slug == "api":
        return api_docs(request)
    article = get_object_or_404(Article, slug=slug, published_at__isnull=False)
    body_html = mark_safe(md.markdown(article.body, extensions=["extra", "toc"]))
    title, description = GUIDES.get(article.slug, (article.title, article.meta_description))
    if not clean_text(description):
        description = Truncator(clean_text(unescape(strip_tags(body_html)))).chars(160)
    if not description:
        description = f"Read {short_name(article.title)}, an educational guide from Form D Explorer."
    ctx = {
        "article": article,
        "body_html": body_html,
        **metadata(title, description),
        "canonical_path": f"/learn/{article.slug}/",
    }
    if article.body.strip():
        ctx.update(placement(request, "article"))
    return render(request, "content/article_detail.html", ctx)


def api_docs(request):
    ctx = {
        "page_title": "SEC Form D API Reference | Form D Explorer",
        "meta_description": (
            "REST API reference for Form D Explorer. Endpoints, authentication, "
            "rate limits, and response formats."
        ),
        "canonical_path": "/learn/api/",
    }
    return render(request, "content/api_docs.html", ctx)


@require_POST
def newsletter_subscribe(request):
    email = (request.POST.get("email") or "").strip().lower()
    if not email or "@" not in email:
        messages.error(request, "Enter a valid email.")
        return redirect("content:article_list")
    sub, _ = NewsletterSubscriber.objects.get_or_create(email=email)
    if sub.unsubscribed_at:
        sub.unsubscribed_at = None
        sub.save(update_fields=["unsubscribed_at"])
    messages.success(request, "Subscribed. You'll get the weekly Form D digest.")
    return redirect("content:article_list")


def newsletter_unsubscribe(request, email: str):
    try:
        sub = NewsletterSubscriber.objects.get(email=email.lower())
    except NewsletterSubscriber.DoesNotExist:
        return render(request, "content/unsubscribed.html", {"email": email, "already": True})
    sub.unsubscribed_at = timezone.now()
    sub.save(update_fields=["unsubscribed_at"])
    return render(request, "content/unsubscribed.html", {"email": email})
