from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from filings.models import IssuerWatch


class Command(BaseCommand):
    help = "Email watchers when their followed issuers have filed since last notified."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        fallback = timezone.now() - timedelta(days=2)
        sent = 0
        for w in IssuerWatch.objects.select_related("user", "issuer").all():
            if not w.user.is_paid:
                continue
            since = w.last_notified_at or fallback
            new = list(
                w.issuer.filings.filter(created_at__gte=since).order_by("-filing_date")
            )
            if not new:
                continue
            body = render_to_string(
                "emails/watch_alert.txt",
                {"watch": w, "filings": new, "site_url": settings.SITE_URL},
            )
            subject = f"[Form D Explorer] {w.issuer.name}: {len(new)} new filing(s)"
            if dry:
                self.stdout.write(f"[dry] to={w.user.email} subject={subject}")
            else:
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [w.user.email])
                w.last_notified_at = timezone.now()
                w.save(update_fields=["last_notified_at"])
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"Watchlist alerts sent: {sent}"))
