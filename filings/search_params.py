"""One validation path for browser, saved-search, API and export filters."""
import re
from datetime import date
from functools import wraps

from django.http import HttpResponseBadRequest, QueryDict


class SearchValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(" ".join(errors.values()))


def normalize_search_params(params):
    normalized = QueryDict("", mutable=True)
    errors = {}
    for key in params:
        values = params.getlist(key) if hasattr(params, "getlist") else params[key]
        if not isinstance(values, (list, tuple)):
            values = [values]
        if any(not isinstance(v, (str, int)) or isinstance(v, bool) for v in values):
            errors[key] = "Search filters must contain text or numbers."
            continue
        normalized.setlist(key, [str(v).strip() for v in values])
    labels = {"min_amount": "Minimum offering", "max_amount": "Maximum offering",
              "min_sold": "Minimum sold", "min_remaining": "Minimum remaining"}
    for key, label in labels.items():
        raw = normalized.get(key, "")
        if not raw:
            continue
        if (not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", raw)
                or len(raw) > 26):
            errors[key] = f"{label} must be a non-negative whole dollar amount."
            continue
        value = int(raw.replace(",", ""))
        if value > 9223372036854775807:
            errors[key] = f"{label} is too large."
        else:
            normalized[key] = str(value)
    for key in ("date_from", "date_to"):
        raw = normalized.get(key, "")
        if not raw:
            continue
        try:
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw):
                raise ValueError
            date.fromisoformat(raw)
        except ValueError:
            errors[key] = "Filing dates must be valid dates in YYYY-MM-DD format."
    if not errors:
        if normalized.get("min_amount") and normalized.get("max_amount"):
            if int(normalized["min_amount"]) > int(normalized["max_amount"]):
                errors["max_amount"] = "Maximum offering must be at least the minimum offering."
        if normalized.get("date_from") and normalized.get("date_to"):
            if normalized["date_from"] > normalized["date_to"]:
                errors["date_to"] = "The end date must be on or after the start date."
    if errors:
        raise SearchValidationError(errors)
    return normalized


def validated_export(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except SearchValidationError as exc:
            return HttpResponseBadRequest(str(exc), content_type="text/plain")
    return wrapped
