from django.contrib.syndication.views import Feed
from django.shortcuts import get_object_or_404
from django.urls import reverse

from .industry import NAME_TO_SLUG, SLUG_TO_NAME
from .models import Filing, Issuer


def _item_title(f: Filing) -> str:
    amt = f.total_offering_amount or 0
    suffix = ""
    if amt >= 1_000_000_000:
        suffix = f" — ${amt/1_000_000_000:.1f}B"
    elif amt >= 1_000_000:
        suffix = f" — ${amt/1_000_000:.0f}M"
    return f"{f.issuer.name} (Form {f.form_type}){suffix}"


def _item_description(f: Filing) -> str:
    bits = [f"Filed {f.filing_date.isoformat()}"]
    if f.industry_group:
        bits.append(f.industry_group)
    if f.issuer.state:
        bits.append(f.issuer.state)
    if f.total_offering_amount:
        bits.append(f"Offering: ${f.total_offering_amount:,}")
    if f.num_investors:
        bits.append(f"{f.num_investors} investors")
    return " · ".join(bits)


class _BaseFilingFeed(Feed):
    feed_type = __import__("django.utils.feedgenerator", fromlist=["Rss201rev2Feed"]).Rss201rev2Feed
    description_template = None

    def item_title(self, item):
        return _item_title(item)

    def item_description(self, item):
        return _item_description(item)

    def item_link(self, item):
        return f"/filing/{item.accession_number}/"

    def item_pubdate(self, item):
        from datetime import datetime, time

        from django.utils import timezone

        return timezone.make_aware(datetime.combine(item.filing_date, time.min))

    def item_guid(self, item):
        return item.accession_number

    def item_guid_is_permalink(self):
        return False


class RecentFeed(_BaseFilingFeed):
    title = "Form D Explorer — Recent filings"
    link = "/recent/"
    description = "The 50 most recent SEC Form D filings."

    def items(self):
        return Filing.objects.select_related("issuer").order_by("-filing_date", "-id")[:50]


class IssuerFeed(_BaseFilingFeed):
    def get_object(self, request, cik):
        return get_object_or_404(Issuer, cik=cik)

    def title(self, obj):
        return f"{obj.name} — Form D filings"

    def link(self, obj):
        return f"/issuer/{obj.url_slug}/"

    def description(self, obj):
        return f"New SEC Form D filings by {obj.name} (CIK {obj.cik})."

    def items(self, obj):
        return obj.filings.select_related("issuer").order_by("-filing_date", "-id")[:50]


class IndustryFeed(_BaseFilingFeed):
    def get_object(self, request, slug):
        name = SLUG_TO_NAME.get(slug)
        if not name:
            from django.http import Http404
            raise Http404
        return {"slug": slug, "name": name}

    def title(self, obj):
        return f"{obj['name']} — Form D filings"

    def link(self, obj):
        return f"/industry/{obj['slug']}/"

    def description(self, obj):
        return f"New SEC Form D filings in {obj['name']}."

    def items(self, obj):
        return (
            Filing.objects.select_related("issuer")
            .filter(industry_group__iexact=obj["name"])
            .order_by("-filing_date", "-id")[:50]
        )


class StateFeed(_BaseFilingFeed):
    def get_object(self, request, state):
        state = state.upper()
        if not Filing.objects.filter(issuer__state=state).exists():
            from django.http import Http404
            raise Http404
        return state

    def title(self, obj):
        return f"{obj} — Form D filings"

    def link(self, obj):
        return f"/state/{obj}/"

    def description(self, obj):
        return f"New SEC Form D filings from issuers in {obj}."

    def items(self, obj):
        return (
            Filing.objects.select_related("issuer")
            .filter(issuer__state=obj)
            .order_by("-filing_date", "-id")[:50]
        )
