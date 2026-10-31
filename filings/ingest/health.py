"""Separate review of already imported metadata from incomplete ingestion."""
from django.db.models import Q


METADATA_REVIEW_ERROR = "SEC index metadata changed; review required"


def review_only_jobs():
    # Match legacy holds too, without reclassifying failed/unimported filings or
    # index failures. A previous successful import is required for this exception.
    return Q(kind="filing", state="held", last_error=METADATA_REVIEW_ERROR,
             last_success_at__isnull=False, outcome__in=("existing", "structured", "metadata"))


def has_ingestion_failures(stats):
    # Fall back to the original backlog for older callers/results: fail closed.
    return bool(stats.get("errors") or stats.get("fatal_error") or
                stats.get("failure_backlog", stats.get("backlog", 0)))
