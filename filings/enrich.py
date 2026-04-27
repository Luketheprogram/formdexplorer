"""Best-effort issuer contact discovery.

Two-stage lookup:
1. Clearbit's free Autocomplete API maps a company name to a domain (no key
   required, lightweight).
2. Hunter.io's Domain Search returns generic contact emails for that domain
   (requires HUNTER_API_KEY env; optional — without it we still surface the
   website).

Many Form D issuers are SPVs or funds with no public web presence at all,
so a result of {} is normal and is cached so we don't re-hit the upstream
APIs on every page load."""

import logging
import re

import requests
from django.conf import settings

from .models import normalize_issuer_name

log = logging.getLogger(__name__)

CLEARBIT_SUGGEST = "https://autocomplete.clearbit.com/v1/companies/suggest"
HUNTER_DOMAIN_SEARCH = "https://api.hunter.io/v2/domain-search"
TIMEOUT = 8

_BAD_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "linkedin.com", "facebook.com", "twitter.com", "x.com",
    "wikipedia.org",
}


def _clean_query(name: str) -> str:
    """Strip 'Fund III LP'-style noise so Clearbit matches the underlying brand."""
    s = normalize_issuer_name(name)
    s = re.sub(r"\b(series|fund|spv|holdings|holding|trust|capital|partners|"
               r"partnership|management|advisors|ventures)\b", "", s)
    s = re.sub(r"\b[ivxlc]+\b", "", s)  # strip roman numerals
    s = re.sub(r"\b\d{4}\b", "", s)     # strip years
    return " ".join(s.split())[:80]


def find_company_domain(name: str) -> str | None:
    q = _clean_query(name)
    if len(q) < 3:
        return None
    try:
        r = requests.get(CLEARBIT_SUGGEST, params={"query": q}, timeout=TIMEOUT)
        r.raise_for_status()
        hits = r.json() or []
    except Exception as exc:  # noqa: BLE001
        log.warning("Clearbit suggest failed for %r: %s", q, exc)
        return None
    for hit in hits:
        domain = (hit.get("domain") or "").lower().strip()
        if not domain or domain in _BAD_DOMAINS:
            continue
        return domain
    return None


def find_emails(domain: str) -> list[str]:
    key = getattr(settings, "HUNTER_API_KEY", "") or ""
    if not key or not domain:
        return []
    try:
        r = requests.get(
            HUNTER_DOMAIN_SEARCH,
            params={"domain": domain, "api_key": key, "limit": 10},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = (r.json() or {}).get("data") or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("Hunter lookup failed for %s: %s", domain, exc)
        return []
    emails = data.get("emails") or []
    # Prefer generic (info@, contact@, hello@); fall back to any.
    generic = [e.get("value") for e in emails if e.get("type") == "generic" and e.get("value")]
    other = [e.get("value") for e in emails if e.get("value") and e.get("value") not in generic]
    return generic + other


def find_contact(issuer_name: str) -> dict:
    """Return {'website', 'email'} — either may be empty."""
    domain = find_company_domain(issuer_name)
    out = {"website": "", "email": ""}
    if not domain:
        return out
    out["website"] = f"https://{domain}"
    emails = find_emails(domain)
    if emails:
        out["email"] = emails[0]
    return out
