"""Local-only research route benchmark using a fresh, disposable SQLite database.

Run from the repository root: .venv/bin/python scripts/benchmark_research.py
Never connects to the configured production database or writes synthetic records there.
For comparisons, copy this harness into isolated checkouts of both revisions and
use the same Python environment, machine and fixture. Output is JSON, not CWV.
"""
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from datetime import date, timedelta
from io import StringIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'

import django
from django.conf import settings


def main():
    with tempfile.TemporaryDirectory(prefix='formd-research-benchmark-') as directory:
        settings.DATABASES = {'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': str(Path(directory) / 'fixture.sqlite3'),
        }}
        settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
        settings.STORAGES['staticfiles']['BACKEND'] = 'django.contrib.staticfiles.storage.StaticFilesStorage'
        settings.ALLOWED_HOSTS = ['testserver']
        settings.DEBUG = True
        settings.ADSENSE_ENABLED = False
        django.setup()
        from django.core.management import call_command
        from django.core.cache import cache
        from django.db import connection
        from django.test import Client
        from django.test.utils import CaptureQueriesContext
        from filings.models import Issuer, Filing

        call_command('migrate', verbosity=0, stdout=StringIO())
        call_command('seed_articles', stdout=StringIO())
        issuers = [Issuer.objects.create(cik=str(9000000+i), name=f'Research fixture {i}', state='CA') for i in range(100)]
        Filing.objects.bulk_create([
            Filing(issuer=issuers[i % 100], accession_number=f'fixture-{i}',
                   filing_date=date(2026, 10, 21)-timedelta(days=i % 730), industry_group='Biotechnology',
                   total_offering_amount=10000000, total_amount_sold=2000000,
                   form_type='D/A' if i % 3 == 0 else 'D', is_amendment=i % 3 == 0, raw_xml='x'*10000)
            for i in range(2000)
        ])
        client = Client()
        rows = []
        for path in ['/', '/state/CA/', '/industry/biotechnology/',
                     '/issuer/research-fixture-0-9000000/', '/filing/fixture-0/']:
            for mode in ['cold', 'warm']:
                times, counts, xml = [], [], []
                cache.clear()
                for _ in range(7):
                    if mode == 'cold':
                        cache.clear()
                    start = time.perf_counter()
                    with CaptureQueriesContext(connection) as queries:
                        response = client.get(path)
                    times.append((time.perf_counter()-start)*1000)
                    counts.append(len(queries))
                    xml.append(sum('"raw_xml"' in q['sql'] for q in queries))
                    if response.status_code != 200:
                        raise RuntimeError(f'{path}: HTTP {response.status_code}')
                rows.append(dict(path=path, cache=mode, median_ms=round(statistics.median(times), 2),
                                 queries=statistics.median(counts), raw_xml_selects=statistics.median(xml),
                                 html_bytes=len(response.content)))
        connection.close()
        print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
