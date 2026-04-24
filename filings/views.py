import csv
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, Min, Sum
from django.db.models.functions import ExtractYear
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .industry import NAME_TO_SLUG, SLUG_TO_NAME
from .models import Filing, Issuer, IssuerWatch, RelatedPerson, SavedSearch
from .search import active_filters, build_filing_query, search_persons


def _aggregate_stats(qs):
    last_365 = timezone.now().date() - timedelta(days=365)
    last_year = qs.filter(filing_date__gte=last_365)
    sane = qs.filter(total_offering_amount__lte=OUTLIER_CAP)
    agg = qs.aggregate(total_filings=Count("id"))
    money = sane.aggregate(
        total_raised=Sum("total_offering_amount"),
        avg_raised=Avg("total_offering_amount"),
    )
    agg.update(money)
    agg["filings_last_year"] = last_year.count()
    return agg

FREE_RESULT_LIMIT = 10
PAYWALL_PEEK = 10
EXPORT_ROW_LIMIT = 5000
OUTLIER_CAP = 10_000_000_000  # $10B — above this is almost always bad data


def _is_paid(request) -> bool:
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and getattr(user, "is_paid", False))


def home(request):
    recent = Filing.objects.select_related("issuer").order_by("-filing_date", "-id")[:20]
    industries = [(name, slug) for name, slug in NAME_TO_SLUG.items()]
    ctx = {
        "recent": recent,
        "industries": industries,
        "page_title": "Form D Explorer — Search SEC Form D Filings",
        "meta_description": (
            "Search SEC Form D filings by company, state, industry, or offering size. "
            "Clean, fast, free."
        ),
    }
    return render(request, "filings/home.html", ctx)


def _capped_count(qs, cap: int = 500) -> tuple[int, bool]:
    """COUNT(*) capped at `cap` so keystroke-driven search stays fast.
    Returns (count, is_capped). If is_capped is True, actual count >= cap."""
    ids = list(qs.order_by().values_list("id", flat=True)[: cap + 1])
    if len(ids) > cap:
        return cap, True
    return len(ids), False


def _search_context(request):
    qs = build_filing_query(request.GET)
    paid = _is_paid(request)
    total, capped = _capped_count(qs)
    if paid:
        visible = list(qs[:500])
        peek: list = []
    else:
        visible = list(qs[:FREE_RESULT_LIMIT])
        peek = list(qs[FREE_RESULT_LIMIT : FREE_RESULT_LIMIT + PAYWALL_PEEK])
    q_text = (request.GET.get("q") or "").strip()
    persons = search_persons(q_text, limit=6) if q_text else []
    return {
        "q": request.GET.get("q", ""),
        "results": visible,
        "peek_results": peek,
        "total": total,
        "total_capped": capped,
        "paid": paid,
        "limit_hit": (not paid) and total > FREE_RESULT_LIMIT,
        "active_filters": active_filters(request.GET),
        "sort": request.GET.get("sort") or ("relevance" if q_text else "newest"),
        "persons": persons,
    }


def search(request):
    ctx = _search_context(request)
    ctx.update({
        "page_title": "Search — Form D Explorer",
        "meta_description": "Search SEC Form D filings by issuer, state, industry, or offering size.",
        "robots": "noindex,follow",
    })
    return render(request, "filings/search.html", ctx)


def search_partial(request):
    return render(request, "_partials/search_results.html", _search_context(request))


def issuer_detail(request, slug_cik: str):
    if "-" not in slug_cik:
        raise Http404
    slug, _, cik = slug_cik.rpartition("-")
    if not cik.isdigit():
        raise Http404
    issuer = get_object_or_404(Issuer, cik=cik)
    filings = issuer.filings.all().order_by("-filing_date")
    page_obj = Paginator(filings, 50).get_page(request.GET.get("page"))
    sane_filings = filings.filter(total_offering_amount__lte=OUTLIER_CAP)
    agg = sane_filings.aggregate(
        total_offered=Sum("total_offering_amount"),
        total_sold=Sum("total_amount_sold"),
    )
    meta = filings.aggregate(
        first_filed=Min("filing_date"),
        last_filed=Max("filing_date"),
        count=Count("id"),
    )
    agg.update(meta)
    by_year = list(
        sane_filings.annotate(year=ExtractYear("filing_date"))
        .values("year")
        .annotate(total=Sum("total_offering_amount"), count=Count("id"))
        .order_by("year")
    )
    max_year_total = max((row["total"] or 0 for row in by_year), default=0)
    industry_slug = NAME_TO_SLUG.get(filings.first().industry_group) if filings.exists() and filings.first().industry_group else None
    related = []
    if issuer.normalized_name:
        related = list(
            Issuer.objects.filter(normalized_name=issuer.normalized_name)
            .exclude(pk=issuer.pk)[:6]
        )
    is_watching = False
    if request.user.is_authenticated:
        is_watching = IssuerWatch.objects.filter(user=request.user, issuer=issuer).exists()
    ctx = {
        "issuer": issuer,
        "filings": filings,
        "page_obj": page_obj,
        "stats": agg,
        "by_year": by_year,
        "max_year_total": max_year_total,
        "industry_slug": industry_slug,
        "related_issuers": related,
        "is_watching": is_watching,
        "page_title": f"{issuer.name} SEC Form D Filings | Form D Explorer",
        "meta_description": (
            f"{issuer.name} (CIK {issuer.cik}) — all SEC Form D filings, offering "
            f"amounts, related persons, and filing history."
        ),
        "canonical_path": f"/issuer/{issuer.url_slug}/",
    }
    return render(request, "filings/issuer_detail.html", ctx)


@login_required
def issuer_watch_toggle(request, cik: str):
    if request.method != "POST":
        return redirect("filings:home")
    if not request.user.is_paid:
        messages.info(request, "Watchlists are a Pro feature.")
        return redirect("subscriptions:pricing")
    issuer = get_object_or_404(Issuer, cik=cik)
    watch = IssuerWatch.objects.filter(user=request.user, issuer=issuer).first()
    if watch:
        watch.delete()
    else:
        IssuerWatch.objects.create(user=request.user, issuer=issuer)
    return redirect(f"/issuer/{issuer.url_slug}/")


def person_detail(request, slug: str):
    qs = RelatedPerson.objects.filter(name_slug=slug).select_related("filing", "filing__issuer")
    if not qs.exists():
        raise Http404
    display_name = qs.first().name
    filings = (
        Filing.objects.filter(related_persons__name_slug=slug)
        .select_related("issuer")
        .distinct()
        .order_by("-filing_date")
    )
    relationships = sorted(set(qs.values_list("relationship", flat=True)) - {""})
    issuers = {}
    for f in filings[:200]:
        issuers.setdefault(f.issuer_id, f.issuer)
    ctx = {
        "display_name": display_name,
        "slug": slug,
        "filings": filings[:100],
        "filings_total": filings.count(),
        "relationships": relationships,
        "issuers": list(issuers.values())[:20],
        "page_title": f"{display_name} — SEC Form D Filings | Form D Explorer",
        "meta_description": (
            f"Every SEC Form D filing where {display_name} is listed as an executive "
            f"officer, director, or promoter."
        ),
        "canonical_path": f"/person/{slug}/",
    }
    return render(request, "filings/person_detail.html", ctx)


@login_required
def watchlist(request):
    watches = request.user.watches.select_related("issuer").order_by("-created_at")
    return render(
        request,
        "filings/watchlist.html",
        {
            "watches": watches,
            "page_title": "Watchlist — Form D Explorer",
            "robots": "noindex",
        },
    )


def filing_detail(request, accession_number: str):
    filing = get_object_or_404(
        Filing.objects.select_related("issuer").prefetch_related("related_persons"),
        accession_number=accession_number,
    )
    # Same issuer, near-in-date Form D / D/A chain.
    window = timedelta(days=365 * 3)
    lineage = (
        Filing.objects.filter(issuer=filing.issuer)
        .exclude(pk=filing.pk)
        .filter(
            filing_date__gte=filing.filing_date - window,
            filing_date__lte=filing.filing_date + window,
        )
        .order_by("-filing_date")[:10]
    )
    ctx = {
        "filing": filing,
        "lineage": list(lineage),
        "page_title": (
            f"Form {filing.form_type} — {filing.issuer.name} ({filing.filing_date}) | Form D Explorer"
        ),
        "meta_description": (
            f"{filing.issuer.name} filed Form {filing.form_type} on {filing.filing_date}. "
            f"Offering details, related persons, and SEC EDGAR link."
        ),
        "canonical_path": f"/filing/{filing.accession_number}/",
    }
    return render(request, "filings/filing_detail.html", ctx)


def _top_issuers(qs, limit: int = 10):
    return list(
        qs.filter(total_offering_amount__lte=OUTLIER_CAP)
        .values("issuer__name", "issuer__cik", "issuer__name_slug")
        .annotate(total_raised=Sum("total_offering_amount"), filing_count=Count("id"))
        .order_by("-total_raised")[:limit]
    )


def industry_detail(request, slug: str):
    name = SLUG_TO_NAME.get(slug)
    if not name:
        raise Http404
    qs = Filing.objects.filter(industry_group__iexact=name)
    stats = _aggregate_stats(qs)
    list_qs = qs.select_related("issuer").order_by("-filing_date")
    top_issuers = _top_issuers(qs)
    paginator = Paginator(list_qs, 50)
    page = paginator.get_page(request.GET.get("page"))
    ctx = {
        "industry": name,
        "slug": slug,
        "page_obj": page,
        "stats": stats,
        "top_issuers": top_issuers,
        "page_title": f"{name} — SEC Form D Filings | Form D Explorer",
        "meta_description": (
            f"Recent SEC Form D filings in {name}. Offering amounts, issuers, and filing history."
        ),
        "canonical_path": f"/industry/{slug}/",
    }
    return render(request, "filings/industry_detail.html", ctx)


def state_detail(request, state: str):
    state_up = state.upper()
    qs = Filing.objects.filter(issuer__state=state_up)
    if not qs.exists():
        raise Http404
    stats = _aggregate_stats(qs)
    list_qs = qs.select_related("issuer").order_by("-filing_date")
    top_issuers = _top_issuers(qs)
    top_industries = list(
        qs.exclude(industry_group="")
        .values("industry_group")
        .annotate(count=Count("id"), total=Sum("total_offering_amount"))
        .order_by("-count")[:8]
    )
    for ind in top_industries:
        ind["slug"] = NAME_TO_SLUG.get(ind["industry_group"])
    paginator = Paginator(list_qs, 50)
    page = paginator.get_page(request.GET.get("page"))
    ctx = {
        "state": state_up,
        "page_obj": page,
        "stats": stats,
        "top_issuers": top_issuers,
        "top_industries": top_industries,
        "page_title": f"{state_up} — SEC Form D Filings | Form D Explorer",
        "meta_description": (
            f"SEC Form D filings from issuers in {state_up}. Offering amounts, industries, dates."
        ),
        "canonical_path": f"/state/{state_up}/",
    }
    return render(request, "filings/state_detail.html", ctx)


def recent(request):
    qs = Filing.objects.select_related("issuer").order_by("-filing_date", "-id")[:50]
    ctx = {
        "filings": qs,
        "page_title": "Recent SEC Form D Filings | Form D Explorer",
        "meta_description": "The 50 most recent SEC Form D filings.",
        "canonical_path": "/recent/",
    }
    return render(request, "filings/recent.html", ctx)


@login_required
def export_csv(request):
    user = request.user
    token = None
    if not user.is_paid:
        token = user.export_tokens.filter(used_at__isnull=True).first()
        if token is None:
            messages.info(request, "CSV export requires Pro or a one-time export purchase.")
            return redirect("subscriptions:pricing")

    qs = build_filing_query(request.GET)[:EXPORT_ROW_LIMIT]
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="form-d-filings.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "accession_number", "form_type", "filing_date", "issuer_name", "cik",
        "state", "industry_group", "total_offering_amount", "total_amount_sold",
        "minimum_investment", "num_investors", "exemptions",
    ])
    for f in qs.iterator():
        writer.writerow([
            f.accession_number, f.form_type, f.filing_date, f.issuer.name, f.issuer.cik,
            f.issuer.state, f.industry_group, f.total_offering_amount, f.total_amount_sold,
            f.minimum_investment, f.num_investors, f.offering_type,
        ])
    if token is not None:
        token.consume()
    return response


@login_required
def saved_search_list(request):
    searches = request.user.saved_searches.all()
    return render(
        request,
        "filings/saved_searches.html",
        {
            "searches": searches,
            "max_searches": 10,
            "page_title": "Saved searches — Form D Explorer",
            "robots": "noindex",
        },
    )


@login_required
def saved_search_create(request):
    if not request.user.is_paid:
        messages.info(request, "Saved search alerts are a Pro feature.")
        return redirect("subscriptions:pricing")
    if request.user.saved_searches.count() >= 10:
        messages.error(request, "You've hit the 10 saved search limit.")
        return redirect("filings:saved_search_list")

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()[:120]
        params = {
            k: v
            for k, v in request.POST.items()
            if k in {"q", "state", "industry", "min_amount", "max_amount", "date_from", "date_to"} and v
        }
        if not name:
            messages.error(request, "Name is required.")
        else:
            SavedSearch.objects.create(user=request.user, name=name, params=params)
            return redirect("filings:saved_search_list")
    return render(
        request,
        "filings/saved_search_form.html",
        {"page_title": "New saved search", "robots": "noindex"},
    )


@login_required
def saved_search_delete(request, pk: int):
    search = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    if request.method == "POST":
        search.delete()
    return redirect("filings:saved_search_list")
