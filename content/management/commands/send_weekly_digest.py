from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from content.models import NewsletterSubscriber
from filings.models import Filing


class Command(BaseCommand):
    help = "Send a weekly digest of the top 10 Form D filings by offering amount."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--days", type=int, default=7)

    def handle(self, *args, **opts):
        since = timezone.now().date() - timedelta(days=opts["days"])
        top = list(
            Filing.objects.select_related("issuer")
            .filter(filing_date__gte=since, total_offering_amount__lte=10_000_000_000)
            .order_by("-total_offering_amount")[:10]
        )
        if not top:
            self.stdout.write("No filings in window, skipping.")
            return
        subs = NewsletterSubscriber.objects.filter(unsubscribed_at__isnull=True)
        sent = 0
        for sub in subs:
            body = render_to_string(
                "emails/weekly_digest.txt",
                {
                    "filings": top,
                    "site_url": settings.SITE_URL,
                    "email": sub.email,
                    "since": since,
                },
            )
            subject = f"[Form D Explorer] Top 10 raises this week"
            if opts["dry_run"]:
                self.stdout.write(f"[dry] to={sub.email}")
            else:
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [sub.email])
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"Digest sent to {sent} subscribers."))
