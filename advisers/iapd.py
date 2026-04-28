"""Thin client over SEC IAPD's public JSON endpoints.

Used both by the on-demand search fallback (when local DB has no/few matches)
and by the ingest_form_adv management command. IAPD doesn't require an API key
but does want a real User-Agent."""

import logging
from typing import Any

import requests
from django.conf import settings

log = logging.getLogger(__name__)

SEARCH_URL = "https://adviserinfo.sec.gov/api/Firm/Search"
DETAIL_URL_TEMPLATE = "https://adviserinfo.sec.gov/api/Firm/{crd}"
TIMEOUT = 12


def _headers() -> dict:
    ua = getattr(settings, "EDGAR_USER_AGENT", "Form D Explorer luke@dawncrestconsulting.com")
    return {"User-Agent": ua, "Accept": "application/json"}


def search(query: str, limit: int = 20) -> list[dict]:
    if not query or len(query.strip()) < 2:
        return []
    try:
        r = requests.get(
            SEARCH_URL,
            params={"query": query.strip(), "hl": "en"},
            headers=_headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json() or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("IAPD search failed for %r: %s", query, exc)
        return []
    hits = data.get("hits") or data.get("results") or []
    return hits[:limit]


def fetch_detail(crd: str) -> dict | None:
    try:
        r = requests.get(
            DETAIL_URL_TEMPLATE.format(crd=crd),
            headers=_headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json() or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("IAPD detail failed for CRD %s: %s", crd, exc)
        return None


def _first(d: dict, *keys, default=""):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return default


def parse_firm(payload: dict) -> dict:
    """Best-effort flatten of IAPD's per-firm JSON response into our schema.
    IAPD's exact field shape varies; we tolerate missing keys and surface
    the raw payload for later re-parsing."""
    if not payload:
        return {}
    info = payload.get("basicInformation") or payload
    addr = (
        payload.get("mainOfficeLocation")
        or payload.get("mainAddress")
        or info.get("officeLocations", [{}])[0]
        if isinstance(info.get("officeLocations"), list)
        else {}
    ) or {}
    if not isinstance(addr, dict):
        addr = {}
    crd = str(_first(info, "firmId", "firmCRD", "crdNumber") or "").strip()
    if not crd:
        return {}
    return {
        "crd": crd,
        "sec_file_number": str(_first(info, "secNumber", "secNo", "iaSecNumber") or "").strip(),
        "name": _first(info, "firmName", "currentLegalName", "name"),
        "street": _first(addr, "streetAddress1", "addressLine1", "street"),
        "city": _first(addr, "city"),
        "state": _first(addr, "state", "addressState")[:8],
        "zip_code": _first(addr, "postalCode", "zipCode")[:16],
        "phone": str(_first(info, "mainPhone", "phone") or "").strip()[:32],
        "website": _first(info, "websiteAddress", "website") or "",
        "regulatory_aum": _to_int(_first(info, "totalRegulatoryAum", "regulatoryAum")),
        "discretionary_aum": _to_int(_first(info, "totalDiscretionaryAum", "discretionaryAum")),
        "num_employees": _to_int(_first(info, "numberOfEmployees", "totalEmployees")),
        "num_clients": _to_int(_first(info, "numberOfClients", "totalClients")),
        "registration_status": _first(info, "registrationStatus", "status"),
        "has_disciplinary": bool(_first(info, "hasDisclosure", "hasDrp", default=False)),
        "raw_data": payload,
    }


def _to_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None
