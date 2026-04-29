"""Best-effort adviser website lookup.

Clearbit's free Autocomplete API maps a company name to a domain. We accept
the top hit only if the returned name has substantial token overlap with
the adviser's name — otherwise 'Goldman Sachs Asset Management' might
silently bind to 'Goldman & Co Real Estate'."""

import logging
import re
import time

import requests
from django.conf import settings
from django.utils import timezone

from .models import Adviser

log = logging.getLogger(__name__)

CLEARBIT_SUGGEST = "https://autocomplete.clearbit.com/v1/companies/suggest"
TIMEOUT = 8

_NOISE = {
    "the", "and", "of", "&", "co", "company", "inc", "incorporated", "corp",
    "corporation", "llc", "ltd", "limited", "lp", "llp", "lllp", "plc",
    "partners", "partnership", "partnerships", "advisors", "advisor",
    "advisers", "adviser", "advisory", "management", "managers", "capital",
    "investments", "investment", "group", "holdings", "holding", "trust",
    "fund", "funds", "ventures", "venture", "asset", "assets", "wealth",
    "financial", "services", "associates", "consulting", "consultants",
    "international", "global", "worldwide", "us", "usa", "america", "north",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")

_BAD_DOMAINS = {
    "linkedin.com", "facebook.com", "twitter.com", "x.com",
    "wikipedia.org", "bloomberg.com", "crunchbase.com", "yelp.com",
    "google.com", "youtube.com", "instagram.com",
}


def _tokens(s: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall((s or "").lower()) if t and t not in _NOISE}


def _name_similarity(a: str, b: str) -> float:
    aw, bw = _tokens(a), _tokens(b)
    if not aw or not bw:
        return 0.0
    return len(aw & bw) / max(len(aw), len(bw))


def _clean_query(name: str) -> str:
    """Clearbit's autocomplete expects 'Vanguard' not 'THE VANGUARD GROUP, INC.'.
    Strip noise tokens and keep the first 1-3 brand-bearing tokens."""
    toks = [t for t in _TOKEN_RE.findall((name or "").lower()) if t and t not in _NOISE]
    return " ".join(toks[:3])[:60]


def find_adviser_domain(adviser_name: str) -> tuple[str, float] | None:
    """Returns (domain, similarity) or None."""
    if not adviser_name or len(adviser_name) < 3:
        return None
    query = _clean_query(adviser_name)
    if len(query) < 3:
        return None
    try:
        r = requests.get(
            CLEARBIT_SUGGEST,
            params={"query": query},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        hits = r.json() or []
    except Exception as exc:  # noqa: BLE001
        log.warning("Clearbit failed for %r: %s", query, exc)
        return None

    best: tuple[str, float] | None = None
    for hit in hits[:6]:
        domain = (hit.get("domain") or "").lower().strip()
        hit_name = hit.get("name") or ""
        if not domain or domain in _BAD_DOMAINS:
            continue
        sim = _name_similarity(adviser_name, hit_name)
        if best is None or sim > best[1]:
            best = (domain, sim)
    return best


def enrich_adviser(adviser: Adviser, min_similarity: float = 0.5,
                   force: bool = False) -> bool:
    """Set adviser.website if a confident match is found.

    Returns True if a website was written. Marks last_enriched via the
    standard updated_at auto-now."""
    if adviser.website and not force:
        return False
    match = find_adviser_domain(adviser.name)
    if match is None:
        return False
    domain, similarity = match
    if similarity < min_similarity:
        return False
    adviser.website = f"https://{domain}"
    adviser.save(update_fields=["website", "updated_at"])
    return True
