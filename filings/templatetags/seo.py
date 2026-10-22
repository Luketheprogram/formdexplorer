import json

from django import template
from django.conf import settings
from django.utils.safestring import mark_safe

from config.seo import canonical_url, noindex

register = template.Library()


@register.simple_tag(takes_context=True)
def seo_canonical(context):
    return canonical_url(context)


@register.simple_tag(takes_context=True)
def seo_robots(context):
    return "noindex, follow" if noindex(context["request"]) else context.get("robots", "")


@register.simple_tag(takes_context=True)
def seo_structured_data(context):
    origin = settings.SITE_URL
    url = canonical_url(context)
    publisher = {"@type": "Organization", "@id": origin + "/#organization",
                 "name": "Form D Explorer", "url": origin + "/"}
    graph = [publisher, {"@type": "WebSite", "@id": origin + "/#website",
                        "name": "Form D Explorer", "url": origin + "/",
                        "publisher": {"@id": publisher["@id"]}}]
    crumbs = [("Home", origin + "/")]
    article = context.get("article")
    issuer = context.get("issuer")
    filing = context.get("filing")
    if article:
        graph.append({
            "@type": "Article", "headline": article.title,
            "description": article.meta_description or article.title,
            "datePublished": article.published_at.isoformat(),
            "dateModified": article.updated_at.isoformat(),
            "author": {"@id": publisher["@id"]}, "publisher": {"@id": publisher["@id"]},
            "mainEntityOfPage": url,
        })
        crumbs.extend([("Guides", origin + "/learn/"), (article.title, url)])
    elif issuer:
        graph.append({"@type": "Organization", "name": issuer.name, "url": url,
                      "identifier": "CIK-" + issuer.cik,
                      "address": {"@type": "PostalAddress", "streetAddress": issuer.street,
                                  "addressLocality": issuer.city, "addressRegion": issuer.state,
                                  "postalCode": issuer.zip_code}})
        crumbs.append((issuer.name, url))
    elif filing:
        crumbs.extend([(filing.issuer.name, origin + f"/issuer/{filing.issuer.url_slug}/"),
                       (f"Form {filing.form_type} — {filing.accession_number}", url)])
    elif context.get("industry") or context.get("state"):
        crumbs.append((context.get("industry") or context["state"], url))
    if len(crumbs) > 1:
        graph.append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": item}
            for i, (name, item) in enumerate(crumbs, 1)
        ]})
    # JSON serialization, not JS escaping/HTML entities; prevent closing the script tag.
    data = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=True)
    data = data.replace("<", "\\u003C").replace(">", "\\u003E").replace("&", "\\u0026")
    return mark_safe('<script type="application/ld+json">' + data + '</script>')
