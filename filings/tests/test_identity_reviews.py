import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from io import BytesIO
from pathlib import Path
from threading import Barrier, Event
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connections, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature, override_settings
from openpyxl import load_workbook

from accounts.models import ExportToken
from filings.ingest.issuers import upsert_issuer
from filings.ingest.xml_parser import ParsedIssuer
from filings.models import Issuer, IssuerIdentityObservation, IssuerIdentityReview
from filings.reviewed_repairs import apply_c3_review, filing_snapshot, issuer_snapshot
from rega.models import Form1AFiling, RegAFilingReview


class ReviewFixture:
    def setUp(self):
        self.plan = json.loads((Path(__file__).parent / 'fixtures/c3_review.json').read_text())
        self.bullion = Issuer.objects.create(id=24218, cik='1981779', name='C3 Bullion, Inc.', name_slug='cik-1981779')
        self.capital = Issuer.objects.create(id=24219, cik='1827424', name='CIK 1827424', name_slug='cik-1827424')
        for pk, issuer, accession in [(1158, self.bullion, '0001981779-23-000005'),
                                     (1159, self.capital, '0001827424-23-000007'),
                                     (1218, self.bullion, '0001981779-24-000001')]:
            Form1AFiling.objects.create(id=pk, issuer=issuer, accession_number=accession,
                filing_date=date(2023, 12, 5), price_per_security=0, total_amount_sold=0,
                net_income=-449060, raw_xml='<source>unchanged</source>')
        self.snapshots = [{'issuer': issuer_snapshot(i), 'url': 'https://formdexplorer.com/issuer/'+i.url_slug+'/',
                           'filings': [filing_snapshot(f) for f in i.rega_filings.all()]}
                          for i in [self.bullion, self.capital]]


@override_settings(SITE_URL="https://formdexplorer.com")
class IdentityReviewTests(ReviewFixture, TestCase):
    def test_exact_scope_and_repeat_rejection(self):
        result = apply_c3_review(self.plan, self.snapshots)
        self.assertEqual(result, {'issuer_fields_updated': 2, 'identity_reviews_created': 1, 'withdrawal_reviews_created': 2})
        self.assertEqual(list(RegAFilingReview.objects.order_by('filing_id').values_list('filing_id', flat=True)), [1159, 1218])
        for old in self.snapshots:
            issuer = Issuer.objects.get(pk=old['issuer']['id'])
            expected = dict(old['issuer'])
            if issuer.pk == 24219: expected.update(name='C3 Capital, Inc.', normalized_name='c3')
            self.assertEqual(issuer_snapshot(issuer), expected)
            self.assertEqual([filing_snapshot(f) for f in issuer.rega_filings.all()], old['filings'])
        with self.assertRaises(ValueError): apply_c3_review(self.plan, self.snapshots)
        self.assertEqual(IssuerIdentityReview.objects.count(), 1)

    def test_failure_after_name_update_rolls_back_everything(self):
        with patch.object(RegAFilingReview, 'save', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError): apply_c3_review(self.plan, self.snapshots)
        self.capital.refresh_from_db()
        self.assertEqual(self.capital.name, 'CIK 1827424')
        self.assertFalse(IssuerIdentityReview.objects.exists())
        self.assertFalse(RegAFilingReview.objects.exists())

    def test_source_or_target_drift_rejects_all_writes(self):
        for key, value in [('target_cik', '1981779'), ('offering_file_number', '024-12367')]:
            plan = copy.deepcopy(self.plan)
            plan['recommended_bundle']['new_review_records'][1][key] = value
            with self.assertRaises(ValueError): apply_c3_review(plan, self.snapshots)
        Form1AFiling.objects.filter(pk=1159).update(raw_xml='changed source')
        with self.assertRaises(ValueError): apply_c3_review(self.plan, self.snapshots)
        self.capital.refresh_from_db()
        self.assertEqual(self.capital.name, 'CIK 1827424')

    def test_future_ingestion_retains_source_identity_without_overwriting_review(self):
        apply_c3_review(self.plan, self.snapshots)
        self.capital.refresh_from_db();before = issuer_snapshot(self.capital)
        parsed = ParsedIssuer(cik='0001827424', name='C3 Bullion, Inc.', jurisdiction='DE', street='New source address')
        for _ in range(2): upsert_issuer(parsed, date(2027, 1, 1), 'future-source')
        self.capital.refresh_from_db()
        self.assertEqual(issuer_snapshot(self.capital), before)
        observation = IssuerIdentityObservation.objects.get()
        self.assertEqual(observation.source_values['name'], 'C3 Bullion, Inc.')
        self.assertEqual(observation.source_values['jurisdiction'], 'DE')
        self.assertEqual(observation.accession_number, 'future-source')

    def test_pages_search_canonicals_and_original_values(self):
        apply_c3_review(self.plan, self.snapshots)
        for path in ['/issuer/cik-1827424-1827424/', '/1a/0001827424-23-000007/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Historical issuer identity')
            self.assertContains(response, 'C3 Capital, Inc.')
            self.assertContains(response, 'href="https://formdexplorer.com'+path+'"')
        response = self.client.get('/1a/0001827424-23-000007/')
        self.assertContains(response, 'Withdrawal filed')
        self.assertContains(response, '0001827424-23-000011')
        self.assertContains(response, '$0.0000')
        self.assertContains(response, 'Form 1-A — C3 Capital, Inc.')
        self.assertNotContains(self.client.get('/1a/0001981779-23-000005/'), 'Withdrawal filed')
        self.assertContains(self.client.get('/1a/0001981779-24-000001/'), 'January 17, 2024')
        for path in ['/1a/?q=Capital', '/1a/partial/?q=Capital']:
            # URLconf uses the search-partial route below if its spelling changes.
            if 'partial' in path:
                from django.urls import reverse
                path = reverse('rega:search_partial')+'?q=Capital'
            response = self.client.get(path)
            self.assertContains(response, 'Historical issuer identity')
            self.assertContains(response, 'Withdrawal filed')

    def test_paid_export_appends_context_without_changing_source_numbers(self):
        apply_c3_review(self.plan, self.snapshots)
        user = get_user_model().objects.create_user(email='review-export@example.com')
        self.client.force_login(user);ExportToken.objects.create(user=user)
        response = self.client.get('/1a/export/xlsx/')
        self.assertEqual(response.status_code, 200)
        rows = list(load_workbook(BytesIO(response.content)).active.values)
        exported = {dict(zip(rows[0], r))['Accession']: dict(zip(rows[0], r)) for r in rows[1:]}
        reviewed = exported['0001827424-23-000007']
        self.assertEqual(reviewed['Issuer'], 'C3 Capital, Inc.')
        self.assertEqual(reviewed['Amount sold ($)'], 0)
        self.assertEqual(reviewed['Filing status'], 'Withdrawal filed')
        self.assertEqual(reviewed['Status filed date'], '2023-12-05')
        self.assertIn('incorrect CIK', reviewed['Status note'])
        self.assertIn('Historical issuer', reviewed['Identity note'])
        self.assertIsNone(exported['0001981779-23-000005']['Filing status'])
        self.assertEqual(exported['0001981779-24-000001']['Status filed date'], '2024-01-17')
        self.assertEqual(self.client.get('/1a/export/xlsx/').status_code, 302)


class IdentityReviewConcurrencyTests(ReviewFixture, TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_two_operators_cannot_apply_twice(self):
        barrier = Barrier(2)
        def run():
            connections.close_all();barrier.wait(timeout=10)
            try:
                apply_c3_review(self.plan, self.snapshots);return 'applied'
            except ValueError: return 'rejected'
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda _: run(), range(2)))
        self.assertEqual(sorted(results), ['applied', 'rejected'])
        self.assertEqual(IssuerIdentityReview.objects.count(), 1)
        self.assertEqual(RegAFilingReview.objects.count(), 2)

    @skipUnlessDBFeature('has_select_for_update')
    def test_ingestion_waits_for_review_then_preserves_identity(self):
        started = Event()
        def ingest():
            connections.close_all();started.set()
            try: upsert_issuer(ParsedIssuer(cik='1827424', name='Conflicting source'), date(2027, 1, 1), 'concurrent')
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                list(Issuer.objects.filter(pk__in=[24218,24219]).order_by('pk').select_for_update())
                future = pool.submit(ingest);self.assertTrue(started.wait(timeout=10))
                apply_c3_review(self.plan, self.snapshots)
            future.result(timeout=20)
        self.capital.refresh_from_db()
        self.assertEqual(self.capital.name, 'C3 Capital, Inc.')
        self.assertEqual(IssuerIdentityObservation.objects.get().source_values['name'], 'Conflicting source')
