import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Barrier, Event
from unittest.mock import patch

from django.db import connections, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature, override_settings

from api.serializers import issuer_dict, filing_dict
from filings.ingest.issuers import upsert_issuer
from filings.ingest.xml_parser import ParsedIssuer
from filings.models import Issuer, Filing, IssuerFieldReview, IssuerFieldObservation
from filings.reviewed_repairs import apply_ym_year_review, issuer_snapshot
from rega.models import Form1AFiling


class YMFixture:
    def setUp(self):
        self.plan = json.loads((Path(__file__).parent/'fixtures/ym_year_review.json').read_text())
        self.issuer = Issuer.objects.create(id=9998, cik='1416299', name='YM Corp', name_slug='ym-corp',
            year_of_incorporation='2025', street='288 EGG HARBOR ROAD', city='SEWELL', jurisdiction='NEVADA')
        # Preserve stale unrelated normalization too: the repair must bypass save().
        Issuer.objects.filter(pk=9998).update(normalized_name='avatar ventures')
        self.issuer.refresh_from_db()
        self.filing = Filing.objects.create(issuer=self.issuer, accession_number='0001416299-26-000002',
            filing_date=date(2026,9,28), raw_xml='<edgarSubmission><primaryIssuer><cik>0001416299</cik><yearOfInc><value>2025</value></yearOfInc></primaryIssuer></edgarSubmission>',
            total_offering_amount=1000000, total_amount_sold=0)
        self.rega = Form1AFiling.objects.create(issuer=self.issuer, accession_number='0001829126-26-007092',
            filing_date=date(2026,7,1), raw_xml='<original>2006</original>')
        self.expected = issuer_snapshot(self.issuer)
        self.sources = {f.accession_number:hashlib.sha256(f.raw_xml.encode()).hexdigest() for f in [self.filing,self.rega]}

    def apply(self):
        return apply_ym_year_review(self.plan,self.expected,self.sources)


@override_settings(SITE_URL='https://formdexplorer.com')
class FieldReviewTests(YMFixture, TestCase):
    def test_only_year_changes_sources_and_unrelated_fields_preserved(self):
        before = list(Filing.objects.values())
        self.assertEqual(self.apply(), {'issuer_fields_updated':1,'field_reviews_created':1,'source_observations_created':1})
        self.issuer.refresh_from_db()
        self.assertEqual(issuer_snapshot(self.issuer),{**self.expected,'year_of_incorporation':'2006'})
        self.assertEqual(before,list(Filing.objects.values()))
        self.assertEqual(IssuerFieldObservation.objects.get().source_value,'2025')
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(IssuerFieldReview.objects.count(),1)

    def test_metadata_only_filings_are_preserved_without_invented_observations(self):
        old = Filing.objects.create(issuer=self.issuer, accession_number='old-metadata-only',
            filing_date=date(2025,1,21), raw_xml='')
        self.sources[old.accession_number] = hashlib.sha256(b'').hexdigest()
        self.assertEqual(self.apply()['source_observations_created'], 1)
        old.refresh_from_db();self.assertEqual(old.raw_xml, '')
        self.assertFalse(IssuerFieldObservation.objects.filter(accession_number=old.accession_number).exists())

    def test_invalid_scope_drift_and_sources_abort(self):
        for key,value in [('field_name','phone'),('cik','1981779'),('reviewed_value','2007')]:
            plan=copy.deepcopy(self.plan);plan[key]=value
            with self.assertRaises(ValueError):apply_ym_year_review(plan,self.expected,self.sources)
        bad=copy.deepcopy(self.sources);bad[self.filing.accession_number]='0'*64
        with self.assertRaises(ValueError):apply_ym_year_review(self.plan,self.expected,bad)
        Issuer.objects.filter(pk=9998).update(phone='changed')
        with self.assertRaises(ValueError):self.apply()
        self.assertFalse(IssuerFieldReview.objects.exists())

    def test_observation_failure_rolls_back_review_and_year(self):
        with patch.object(IssuerFieldObservation.objects,'create',side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):self.apply()
        self.issuer.refresh_from_db()
        self.assertEqual(issuer_snapshot(self.issuer),self.expected)
        self.assertFalse(IssuerFieldReview.objects.exists())

    def test_newer_older_blank_and_repeated_source_values_kept_field_scoped(self):
        self.apply()
        future=ParsedIssuer(cik='1416299',name='YM Corp',year_of_incorporation='2025',phone='new contact')
        for _ in range(2):upsert_issuer(future,date(2027,1,1),'new')
        for value in ['','2006','2024']:
            upsert_issuer(ParsedIssuer(cik='1416299',year_of_incorporation=value,phone='older'),date(2020,1,1),'old-'+value)
        self.issuer.refresh_from_db()
        self.assertEqual(self.issuer.year_of_incorporation,'2006')
        self.assertEqual(self.issuer.phone,'new contact')
        self.assertEqual(self.issuer.name_slug,'ym-corp')
        self.assertEqual(IssuerFieldObservation.objects.count(),5)
        self.assertEqual(set(IssuerFieldObservation.objects.values_list('source_value',flat=True)),{'2025','','2006','2024'})
        self.filing.refresh_from_db();self.assertIn('<value>2025</value>',self.filing.raw_xml)

    def test_replay_existing_accession_does_not_duplicate_observation(self):
        self.apply()
        upsert_issuer(ParsedIssuer(cik='1416299',year_of_incorporation='2025'),date(2026,9,28),self.filing.accession_number)
        self.assertEqual(IssuerFieldObservation.objects.count(),1)

    def test_pages_and_api_distinguish_reviewed_from_source_values(self):
        self.apply();self.issuer.refresh_from_db();self.filing.refresh_from_db()
        for path in ['/issuer/ym-corp-1416299/','/filing/0001416299-26-000002/']:
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertContains(response,'Reviewed incorporation year: 2006')
            self.assertContains(response,'September 2026 Form D filings report 2025')
            self.assertContains(response,'https://formdexplorer.com'+path)
            self.assertContains(response,'reported year: 2025')
        response=self.client.get('/filing/0001416299-26-000002/')
        self.assertContains(response,'Year incorporated (reviewed)')
        data=filing_dict(self.filing)
        self.assertEqual(data['issuer']['year_of_incorporation'],'2006')
        self.assertEqual(data['issuer']['field_reviews']['year_of_incorporation']['basis'],'reviewed_issuer_value')
        self.assertEqual(data['total_amount_sold'],0)
        self.assertEqual(data['issuer']['field_reviews']['year_of_incorporation']['sources'],self.plan['sources'])

    def test_unreviewed_issuer_behavior_remains_unchanged(self):
        other=upsert_issuer(ParsedIssuer(cik='42',name='Other',year_of_incorporation='2020'),date(2026,1,1),'other')
        self.assertEqual(other.year_of_incorporation,'2020')
        self.assertNotIn('field_reviews',issuer_dict(other))
        self.assertFalse(IssuerFieldObservation.objects.exists())


class FieldReviewConcurrencyTests(YMFixture, TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_two_operators_only_one_commit(self):
        barrier=Barrier(2)
        def work():
            connections.close_all();barrier.wait(timeout=10)
            try:self.apply();return 'applied'
            except ValueError:return 'rejected'
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:work(),range(2)))
        self.assertEqual(sorted(results),['applied','rejected'])
        self.assertEqual(IssuerFieldReview.objects.count(),1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_ingestion_after_review_preserves_year_updates_other_fields(self):
        started=Event()
        def ingest():
            connections.close_all();started.set()
            try:upsert_issuer(ParsedIssuer(cik='1416299',year_of_incorporation='2025',phone='new phone'),date(2027,1,1),'concurrent')
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Issuer.objects.select_for_update().get(pk=9998)
                future=pool.submit(ingest);self.assertTrue(started.wait(timeout=10));self.apply()
            future.result(timeout=20)
        self.issuer.refresh_from_db();self.assertEqual(self.issuer.year_of_incorporation,'2006');self.assertEqual(self.issuer.phone,'new phone')
        self.assertEqual(IssuerFieldObservation.objects.get(accession_number='concurrent').source_value,'2025')

    @skipUnlessDBFeature('has_select_for_update')
    def test_ingestion_first_forces_operator_to_revalidate(self):
        started=Event()
        def apply_review():
            connections.close_all();started.set()
            try:
                self.apply();return 'applied'
            except ValueError:return 'rejected'
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Issuer.objects.select_for_update().get(pk=9998)
                future=pool.submit(apply_review);self.assertTrue(started.wait(timeout=10))
                upsert_issuer(ParsedIssuer(cik='1416299',year_of_incorporation='2025',phone='new phone'),date(2027,1,1),'first')
            self.assertEqual(future.result(timeout=20),'rejected')
        self.assertFalse(IssuerFieldReview.objects.exists())
