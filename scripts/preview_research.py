"""Local-only quality preview using a disposable SQLite database.

Run .venv/bin/python scripts/preview_research.py, then browse 127.0.0.1:8767.
All records are explicitly synthetic fixtures. Never reads/writes a production
DB or sends email. Ctrl-C stops the server and deletes the preview database.
"""
import os
from pathlib import Path
import sys
import tempfile
from datetime import timedelta
from io import StringIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

import django
from django.conf import settings


def main():
    with tempfile.TemporaryDirectory(prefix="formd-quality-preview-") as directory:
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(Path(directory) / "fixture.sqlite3")}}
        settings.DEBUG = True
        settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
        settings.SITE_URL = "http://127.0.0.1:8767"
        settings.SEO_INDEXING_ENABLED = False
        settings.ADSENSE_ENABLED = False
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        settings.STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"
        django.setup()
        from django.core.management import call_command
        from django.utils import timezone
        from filings.models import Filing, Issuer
        from filings.intelligence import month_offset
        call_command("migrate", verbosity=0, stdout=StringIO())
        call_command("seed_articles", stdout=StringIO())
        today = timezone.localdate()
        issuers = [Issuer.objects.create(cik=str(9000001+i), name=f"Synthetic preview issuer {i+1} (test data)", state=state, inferred_at=timezone.now())
                   for i, state in enumerate(["CA", "NY", "TX"])]
        for month in range(-11, 1):
            for index in range(3 + (month+11) % 5):
                issuer = issuers[index % 3]
                amendment = index % 3 == 0
                Filing.objects.create(issuer=issuer, accession_number=f"0099999999-26-{(month+11)*10+index:06}",
                    filing_date=min(month_offset(today, month)+timedelta(days=index), today), form_type="D/A" if amendment else "D",
                    is_amendment=amendment, industry_group="Biotechnology" if index % 2 else "Other Technology",
                    total_offering_amount=10000000 if index % 4 else None,
                    total_amount_sold=(month+12)*100000 if index % 4 else None, num_investors=index)
        print("Synthetic preview only. http://127.0.0.1:8767/research/", flush=True)
        call_command("runserver", "127.0.0.1:8767", use_reloader=False)


if __name__ == "__main__":
    main()
