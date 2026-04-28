"""Multi-strategy fuzzy linker between Adviser firms and Form D Issuers.

The naming pattern in private capital is:
  Adviser  : "Acme Capital Management LLC"
  Issuer   : "Acme Ventures Fund III LP", "Acme Capital Co-Invest 2024 LP"

Exact normalized_name matches catch only ~10% of real pairs. We add:
  1. core-brand-prefix: strip 'capital/management/partners/ventures/fund/...'
     from both sides and require the leading 1-3 tokens to match.
  2. substring inclusion in either direction.
  3. trigram similarity (>=0.45) on Postgres.

Each match carries a confidence label so the template can sort high → low."""

from __future__ import annotations

import re

from django.db import connection
from django.db.models import Q

from filings.models import Issuer

_NOISE_TOKENS = {
    "capital", "management", "partners", "partnership", "ventures",
    "fund", "funds", "holdings", "holding", "trust", "advisors", "advisers",
    "group", "company", "co", "co-invest", "coinvest", "lp", "llp", "llc",
    "inc", "corp", "corporation", "ltd", "the", "and",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _is_postgres() -> bool:
    return connection.vendor == "postgresql"


def _core_tokens(normalized: str) -> list[str]:
    """Strip noise tokens; keep the brand-bearing prefix tokens in order."""
    if not normalized:
        return []
    toks = [t for t in _TOKEN_RE.findall(normalized.lower()) if t and t not in _NOISE_TOKENS]
    return toks


def _core_prefix(normalized: str, n: int = 2) -> str:
    return " ".join(_core_tokens(normalized)[:n])


def find_matching_issuers(adviser, limit: int = 12) -> list[dict]:
    """Return [{issuer, confidence}] ordered high → low."""
    norm = (adviser.normalized_name or "").strip()
    if not norm:
        return []

    seen_ids: set[int] = set()
    out: list[dict] = []

    def _add(qs, confidence: str):
        for issuer in qs.exclude(id__in=seen_ids)[: limit - len(out)]:
            seen_ids.add(issuer.id)
            out.append({"issuer": issuer, "confidence": confidence})
            if len(out) >= limit:
                return

    # 1. Exact normalized match
    _add(Issuer.objects.filter(normalized_name=norm).order_by("name"), "high")
    if len(out) >= limit:
        return out

    # 2. Adviser brand prefix appears at the start of issuer name
    prefix = _core_prefix(norm, n=2)
    if prefix and len(prefix) >= 3:
        _add(
            Issuer.objects.filter(normalized_name__startswith=prefix).order_by("name"),
            "high",
        )
        if len(out) >= limit:
            return out
        _add(
            Issuer.objects.filter(
                Q(normalized_name__icontains=" " + prefix + " ")
                | Q(normalized_name__icontains=prefix + " ")
            ).order_by("name"),
            "medium",
        )
        if len(out) >= limit:
            return out

    # 3. Trigram similarity on Postgres
    if _is_postgres():
        from django.contrib.postgres.search import TrigramSimilarity

        _add(
            Issuer.objects.annotate(sim=TrigramSimilarity("normalized_name", norm))
            .filter(sim__gte=0.45)
            .order_by("-sim", "name"),
            "medium",
        )
        if len(out) >= limit:
            return out

    # 4. First brand-token match (lower precision; only if nothing yet found)
    if not out:
        first = _core_tokens(norm)[:1]
        if first:
            _add(
                Issuer.objects.filter(normalized_name__icontains=first[0]).order_by("name")[:limit],
                "low",
            )
    return out


def find_matching_advisers(issuer, limit: int = 5) -> list[dict]:
    """Reverse direction: which advisers likely run this issuer?"""
    from .models import Adviser

    norm = (issuer.normalized_name or "").strip()
    if not norm:
        return []

    seen_ids: set[int] = set()
    out: list[dict] = []

    def _add(qs, confidence: str):
        for adviser in qs.exclude(id__in=seen_ids)[: limit - len(out)]:
            seen_ids.add(adviser.id)
            out.append({"adviser": adviser, "confidence": confidence})
            if len(out) >= limit:
                return

    _add(Adviser.objects.filter(normalized_name=norm).order_by("name"), "high")
    if len(out) >= limit:
        return out

    # Adviser brand prefix appears at the start of issuer name
    issuer_prefix = _core_prefix(norm, n=2)
    if issuer_prefix and len(issuer_prefix) >= 3:
        _add(
            Adviser.objects.filter(normalized_name__startswith=issuer_prefix).order_by("name"),
            "high",
        )
        if len(out) >= limit:
            return out
        _add(
            Adviser.objects.filter(
                Q(normalized_name__icontains=issuer_prefix + " ")
                | Q(normalized_name__icontains=" " + issuer_prefix)
            ).order_by("name"),
            "medium",
        )
        if len(out) >= limit:
            return out

    if _is_postgres():
        from django.contrib.postgres.search import TrigramSimilarity

        _add(
            Adviser.objects.annotate(sim=TrigramSimilarity("normalized_name", norm))
            .filter(sim__gte=0.45)
            .order_by("-sim", "name"),
            "medium",
        )
    return out
