from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from filings.models import SavedSearch
from filings.search import build_filing_query


class Command(BaseCommand):
    help = "Run each user's saved searches against new filings and email matches."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--lookback-days", type=int, default=1)

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        fallback_since = timezone.now() - timedelta(days=opts["lookback_days"])

        sent = 0
        for ss in SavedSearch.objects.select_related("user").all():
            if not ss.user.is_paid:
                continue
            since = (ss.last_checked_at or fallback_since).date()
            qs = build_filing_query(ss.params).filter(filing_date__gte=since)[:100]
            results = list(qs)
            if not results:
                if not dry:
                    ss.last_checked_at = timezone.now()
                    ss.save(update_fields=["last_checked_at"])
                continue
            body = render_to_string(
                "emails/saved_search_alert.txt",
                {"search": ss, "results": results, "site_url": settings.SITE_URL},
            )
            subject = f"[Form D Explorer] {len(results)} new match(es) for '{ss.name}'"
            if dry:
                self.stdout.write(f"[dry] to={ss.user.email} subject={subject}")
            else:
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [ss.user.email])
                ss.last_checked_at = timezone.now()
                ss.save(update_fields=["last_checked_at"])
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"Alerts processed: {sent}"))
