import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from threading import Barrier, Event
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, skipUnlessDBFeature, override_settings
from django.utils import timezone
from requests import HTTPError, Response, Timeout

from crowdfunding.ingest.pipeline import FormCPipeline
from filings.ingest.calendar import expected_closure
from filings.ingest.edgar_client import EdgarClient, retry_after_seconds
from filings.ingest.index_parser import IndexEntry, parse_form_idx, primary_doc_url
from filings.ingest.monitoring import freshness_report
from filings.ingest.pipeline import IngestPipeline
from filings.ingest.reliability import claim, complete, locked_job, LostLease, failed
from filings.models import Filing, Issuer, IngestionJob, IngestionRun, IngestionSource
from rega.ingest.documents import primary_document, UnsupportedDocument
from rega.ingest.pipeline import Form1APipeline, FORM_1A_TYPES
from rega.models import Form1AFiling, RegAFilingReview

DAY = date(2026, 10, 20)
ACC = "0000000123-26-000001"
ENTRY = IndexEntry("D", "Example Company", "123", "20261020", f"edgar/data/123/{ACC}.txt")
D_XML = b'<edgarSubmission><submissionType>D</submissionType><primaryIssuer><cik>123</cik><entityName>Source Name</entityName></primaryIssuer><offeringData><offeringSalesAmounts><totalOfferingAmount>0</totalOfferingAmount></offeringSalesAmounts></offeringData></edgarSubmission>'


def index_bytes(entry=ENTRY):
    return ("Form Type   Company Name   CIK   Date Filed   File Name\n-----------------\n"
            f"{entry.form_type}   {entry.company}   {entry.cik}   {entry.filing_date}   {entry.filename}\n").encode()


def http_error(status):
    response = Response()
    response.status_code = status
    return HTTPError(response=response)


def html_submission(entry):
    return (f"<SEC-HEADER>\nACCESSION NUMBER: {ACC}\nCENTRAL INDEX KEY: 0000000123\n"
            f"CONFORMED SUBMISSION TYPE: {entry.form_type}\nFILED AS OF DATE: 20261020\n</SEC-HEADER>\n"
            f"<DOCUMENT><TYPE>{entry.form_type}\n<TEXT><html><body>Original source $0</body></html></TEXT></DOCUMENT>").encode()


class FakeSEC:
    def __init__(self, entry=ENTRY, document=D_XML):
        self.entry = entry
        self.document = document
        self.calls = []

    def get_bytes(self, path):
        self.calls.append(path)
        if path.endswith('.idx'):
            return index_bytes(self.entry)
        if isinstance(self.document, Exception):
            raise self.document
        return self.document


class HTTPAndIndexTests(SimpleTestCase):
    def test_space_form_types_and_new_rega_forms(self):
        for form in FORM_1A_TYPES:
            entry = IndexEntry(form, 'ABC LLC', '123', '20261020', ENTRY.filename)
            self.assertEqual(parse_form_idx(index_bytes(entry).decode(), FORM_1A_TYPES, strict=True), [entry])

    def test_malformed_index_or_block_page_cannot_be_empty_success(self):
        for body in ('<html>Denied</html>', 'Form Type File Name\n----\nD malformed row'):
            with self.assertRaises(ValueError):
                parse_form_idx(body, strict=True)
        self.assertEqual(parse_form_idx('Form Type File Name\n----\n', strict=True), [])

    @patch('filings.ingest.edgar_client.time.sleep')
    def test_transient_retry_and_retry_after(self, sleep):
        client = EdgarClient()
        client.limiter = Mock()
        rate_error = http_error(429)
        rate_error.response.headers['Retry-After'] = '7'
        # Real Response objects exercise raise_for_status and the exception type.
        rate_error.response._content = b'busy'
        rate_error.response.raw = Mock()
        ok = Response(); ok.status_code = 200; ok._content = b'ok'; ok._content_consumed = True
        client.session.get = Mock(side_effect=[rate_error.response, ok])
        self.assertEqual(client.get_bytes('/Archives/example'), b'ok')
        sleep.assert_called_once_with(7.0)
        self.assertEqual(client.limiter.wait.call_count, 2)

    @patch('filings.ingest.edgar_client.time.sleep')
    def test_permanent_and_long_retry_after_are_not_hammered(self, sleep):
        for status, delay in ((403, ''), (404, ''), (429, '900')):
            client = EdgarClient(); client.limiter = Mock()
            response = Response(); response.status_code = status; response.headers['Retry-After'] = delay
            response.raw = Mock()
            client.session.get = Mock(return_value=response)
            with self.assertRaises(HTTPError): client.get('/Archives/example')
            self.assertEqual(client.session.get.call_count, 1)
            response.raw.close.assert_called_once()
        sleep.assert_not_called()

    @patch('filings.ingest.edgar_client.time.sleep')
    def test_network_retries_are_bounded(self, sleep):
        client = EdgarClient(); client.limiter = Mock()
        client.session.get = Mock(side_effect=Timeout('offline'))
        with self.assertRaises(Timeout): client.get('/Archives/example')
        self.assertEqual(client.session.get.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_oversized_source_is_rejected_not_truncated(self):
        client = EdgarClient()
        response = Mock()
        response.iter_content.return_value = iter([b'x' * (1024 * 1024)] * 65)
        client.get = Mock(return_value=response)
        with self.assertRaisesRegex(ValueError, '64 MiB'):
            client.get_bytes('/Archives/example')
        response.close.assert_called_once()

    def test_calendar_observed_dates_and_good_friday(self):
        for day in (date(2026, 7, 3), date(2026, 10, 12), date(2027, 12, 31)):
            self.assertTrue(expected_closure(day))
        self.assertFalse(expected_closure(date(2026, 4, 3)))


class DurablePipelineTests(TestCase):
    def run_pipeline(self, client=None, **kwargs):
        return IngestPipeline(client=client or FakeSEC()).run(DAY, DAY, **kwargs)

    def due(self, kind='filing'):
        IngestionJob.objects.filter(kind=kind).update(next_attempt_at=timezone.now()-timedelta(seconds=1))

    def test_success_atomic_archive_and_repeat_preserves_sources_values_and_urls(self):
        stats = self.run_pipeline()
        self.assertEqual(stats['upserted'], 1)
        filing = Filing.objects.get()
        before = list(Filing.objects.values())
        issuer_before = list(Issuer.objects.values())
        self.assertEqual(filing.total_offering_amount, 0)
        source = IngestionSource.objects.get(job__kind='filing')
        self.assertEqual(bytes(source.content), D_XML)
        self.assertEqual(source.sha256, hashlib.sha256(D_XML).hexdigest())
        client = FakeSEC(document=b'<changed/>')
        stats = self.run_pipeline(client)
        self.assertEqual(stats['upserted'], 0)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(before, list(Filing.objects.values()))
        self.assertEqual(issuer_before, list(Issuer.objects.values()))
        self.assertEqual(IngestionSource.objects.count(), 2)

    def test_existing_historical_filing_not_rewritten(self):
        issuer = Issuer.objects.create(cik='123', name='Reviewed name', name_slug='existing-url')
        Filing.objects.create(issuer=issuer, accession_number=ACC, filing_date=DAY, raw_xml='<original/>', total_amount_sold=77)
        before = list(Filing.objects.values())
        self.assertEqual(self.run_pipeline()['existing'], 1)
        self.assertEqual(before, list(Filing.objects.values()))
        issuer.refresh_from_db(); self.assertEqual(issuer.name_slug, 'existing-url')
        self.assertEqual(issuer.name, 'Reviewed name')

    def test_download_failure_retries_outside_lookback_without_false_success(self):
        stats = self.run_pipeline(FakeSEC(document=Timeout('offline')))
        job = IngestionJob.objects.get(kind='filing')
        self.assertEqual((stats['errors'], job.state, job.attempts), (1, 'pending', 1))
        self.assertFalse(Filing.objects.exists())
        self.assertGreater(job.next_attempt_at, timezone.now())
        self.due()
        client = FakeSEC()
        # No business day in this range, so only old durable work runs.
        stats = IngestPipeline(client=client).run(date(2026, 10, 24), date(2026, 10, 24))
        self.assertEqual(stats['upserted'], 1)
        job.refresh_from_db(); self.assertEqual(job.state, 'succeeded')

    def test_index_failure_is_durable_and_recovers_older_day(self):
        client = Mock(); client.get_bytes.side_effect = http_error(503)
        stats = self.run_pipeline(client)
        self.assertEqual(stats['errors'], 1)
        self.assertEqual(IngestionJob.objects.get(kind='index').state, 'pending')
        self.due('index')
        self.run_pipeline()
        self.assertEqual(Filing.objects.count(), 1)

    def test_due_time_not_reset_by_lookback(self):
        self.run_pipeline(FakeSEC(document=Timeout('offline')))
        client = FakeSEC()
        self.run_pipeline(client)
        self.assertEqual(IngestionJob.objects.get(kind='filing').attempts, 1)
        self.assertEqual(client.calls, [client.calls[0]])
        self.assertTrue(client.calls[0].endswith('.idx'))

    def test_failure_after_write_rolls_back_filing_issuer_and_checkpoint(self):
        with patch('filings.ingest.reliability.complete', side_effect=lambda job, outcome: (_ for _ in ()).throw(RuntimeError('checkpoint failed')) if job.kind == 'filing' else complete(job, outcome)):
            self.assertEqual(self.run_pipeline()['errors'], 1)
        self.assertFalse(Filing.objects.exists()); self.assertFalse(Issuer.objects.exists())
        self.assertEqual(IngestionJob.objects.get(kind='filing').state, 'pending')
        # Successfully downloaded source is retained for diagnosing the failure.
        self.assertEqual(bytes(IngestionSource.objects.get(job__kind='filing').content), D_XML)
        self.due(); self.run_pipeline()
        self.assertEqual(Filing.objects.count(), 1)

    def test_claim_records_attempt_in_the_same_database_statement(self):
        job = IngestionJob.objects.create(dataset='d', kind='filing', key=ACC, source_date=DAY)
        # No follow-up model save may be required after ownership is committed.
        with patch.object(IngestionJob, 'save', side_effect=RuntimeError('process stopped before save')):
            token = claim(job.pk)
        job.refresh_from_db()
        self.assertEqual((job.lease_token, job.attempts, job.state), (token, 1, 'running'))

    def test_expired_worker_cannot_commit_after_reclaim(self):
        job = IngestionJob.objects.create(dataset='d', kind='filing', key=ACC, source_date=DAY, entry=asdict(ENTRY))
        old = claim(job.pk)
        IngestionJob.objects.filter(pk=job.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
        new = claim(job.pk)
        self.assertIsNotNone(new); self.assertNotEqual(old, new)
        with transaction.atomic(), self.assertRaises(LostLease): locked_job(job.pk, old)
        with transaction.atomic(): complete(locked_job(job.pk, new), 'existing')
        self.assertIsNone(claim(job.pk))

    def test_repeated_worker_crashes_exhaust_retry_budget(self):
        job = IngestionJob.objects.create(dataset='d', kind='filing', key=ACC, source_date=DAY)
        for _ in range(8):
            self.assertIsNotNone(claim(job.pk))
            IngestionJob.objects.filter(pk=job.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
        self.assertIsNone(claim(job.pk))
        job.refresh_from_db()
        self.assertEqual((job.state, job.attempts), ('held', 8))

    def test_attempt_cap_holds_and_explicit_retry_keeps_provenance(self):
        for _ in range(8):
            self.due()
            self.run_pipeline(FakeSEC(document=Timeout('offline')))
        job = IngestionJob.objects.get(kind='filing')
        self.assertEqual((job.state, job.attempts), ('held', 8))
        self.run_pipeline(); self.assertFalse(Filing.objects.exists())
        call_command('retry_ingestion_job', job.pk, note='Transport restored', stdout=StringIO())
        self.run_pipeline(); self.assertEqual(Filing.objects.count(), 1)
        self.assertTrue(IngestionRun.objects.filter(stats__operator_retry=job.pk).exists())

    def test_retry_after_survives_process_exit(self):
        error = http_error(429); error.response.headers['Retry-After'] = '7200'
        self.run_pipeline(FakeSEC(document=error))
        self.assertGreater(IngestionJob.objects.get(kind='filing').next_attempt_at, timezone.now()+timedelta(minutes=119))

    def test_holiday_404_is_recorded_but_other_failures_remain_errors(self):
        client = Mock(); client.get_bytes.side_effect = http_error(404)
        stats = IngestPipeline(client=client).run(date(2026, 10, 12), date(2026, 10, 12))
        self.assertEqual(stats['errors'], 0)
        self.assertEqual(IngestionJob.objects.get().outcome, 'scheduled_closure')
        self.assertGreaterEqual(self.run_pipeline(client)['errors'], 1)

    def test_malformed_xml_is_not_imported_as_empty_filing(self):
        for body in (b'<html>SEC access denied</html>', b'<edgarSubmission>', b'<edgarSubmission/>', D_XML.replace(b'<submissionType>D<', b'<submissionType>D/A<')):
            self.due()
            self.assertEqual(self.run_pipeline(FakeSEC(document=body))['errors'], 1)
        self.assertFalse(Filing.objects.exists())

    def test_coissuer_index_rows_choose_existing_primary_without_rewriting(self):
        issuer = Issuer.objects.create(cik='123', name='Reviewed name', name_slug='stable')
        Filing.objects.create(issuer=issuer, accession_number=ACC, filing_date=DAY, raw_xml='original')
        other = IndexEntry('D', 'Coissuer', '456', '20261020', ENTRY.filename.replace('/123/', '/456/'))
        client = FakeSEC()
        client.get_bytes = Mock(return_value=index_bytes(other) + index_bytes(ENTRY).split(b'-----------------\n')[1])
        stats = self.run_pipeline(client)
        self.assertEqual((stats['errors'], stats['existing']), (0, 1))
        self.assertEqual(len(IngestionJob.objects.get(kind='filing').entry['index_candidates']), 2)
        self.assertEqual(Filing.objects.get().raw_xml, 'original')
        self.assertEqual(client.get_bytes.call_count, 1)

    def test_new_coissuer_accession_selects_explicit_xml_primary_cik(self):
        other = IndexEntry('D', 'Coissuer', '456', '20261020', ENTRY.filename.replace('/123/', '/456/'))
        client = FakeSEC()
        def fetch(path):
            return (index_bytes(other) + index_bytes(ENTRY).split(b'-----------------\n')[1]) if path.endswith('.idx') else D_XML
        client.get_bytes = Mock(side_effect=fetch)
        stats = self.run_pipeline(client)
        self.assertEqual((stats['errors'], stats['upserted']), (0, 1))
        self.assertEqual(Filing.objects.get().issuer.cik, '123')
        self.assertEqual(Issuer.objects.count(), 1)
        self.assertEqual(IngestionJob.objects.get(kind='filing').entry['cik'], '123')

    def test_one_changed_accession_does_not_block_other_discoveries(self):
        self.run_pipeline()
        changed = IndexEntry('D', 'Changed', '456', '20261020', ENTRY.filename)
        new = IndexEntry('D', 'Example Company', '123', '20261020', ENTRY.filename.replace('000001.txt', '000002.txt'))
        client = FakeSEC()
        client.get_bytes = Mock(side_effect=lambda path: (index_bytes(changed) + index_bytes(new).split(b'-----------------\n')[1]) if path.endswith('.idx') else D_XML)
        stats = self.run_pipeline(client)
        self.assertEqual((stats['errors'], stats['upserted']), (1, 1))
        self.assertEqual(IngestionJob.objects.get(kind='index').state, 'succeeded')
        self.assertEqual(IngestionJob.objects.get(kind='filing', key=ACC).state, 'held')
        self.assertEqual(Filing.objects.count(), 2)

    def test_index_changed_cik_is_held_without_mutating_existing_data(self):
        self.run_pipeline()
        changed = IndexEntry('D', 'Another', '456', '20261020', ENTRY.filename)
        before = list(Filing.objects.values())
        self.assertEqual(self.run_pipeline(FakeSEC(changed))['errors'], 1)
        self.assertEqual(before, list(Filing.objects.values()))

    def test_scheduler_gap_queues_missing_days_but_limits_downloads(self):
        IngestionJob.objects.create(dataset='d', kind='index', key='2026-09-01', source_date=date(2026,9,1),
            state='succeeded', last_success_at=timezone.now(), outcome='indexed')
        client = FakeSEC(); client.get_bytes = Mock(return_value=b'Form Type File Name\n----\n')
        stats = self.run_pipeline(client, retry_limit=2)
        self.assertEqual(client.get_bytes.call_count, 2)
        self.assertTrue(IngestionJob.objects.filter(key='2026-09-02').exists())
        self.assertGreater(stats['backlog'], 20)


@override_settings(SITE_URL='https://formdexplorer.com')
class CoverageTests(TestCase):
    def test_html_rega_preserves_issuer_and_archive_and_unknown_financials(self):
        issuer = Issuer.objects.create(cik='123', name='Reviewed identity', name_slug='original-url', year_of_incorporation='2006')
        before = list(Issuer.objects.values())
        entry = IndexEntry('1-A-W', 'Wrong index name', '123', '20261020', ENTRY.filename)
        submission = html_submission(entry)
        client = FakeSEC(entry)
        def fetch(path):
            if path.endswith('.idx'): return index_bytes(entry)
            if path.endswith('.xml'): raise http_error(404)
            return submission
        client.get_bytes = Mock(side_effect=fetch)
        stats = Form1APipeline(client=client).run(DAY, DAY)
        self.assertEqual(stats['metadata'], 1)
        filing = Form1AFiling.objects.get()
        self.assertEqual((filing.form_type, filing.total_offering_amount, filing.raw_xml), ('1-A-W', None, ''))
        self.assertEqual(before, list(Issuer.objects.values()))
        self.assertFalse(RegAFilingReview.objects.exists())
        self.assertEqual(bytes(IngestionSource.objects.get(job__kind='filing').content), submission)
        response = self.client.get(f'/1a/{ACC}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'https://formdexplorer.com/1a/{ACC}/')
        self.assertContains(response, '1-A-W')
        self.assertContains(response, 'Reviewed identity')
        self.assertContains(self.client.get('/1a/'), '1-A-W')

    def test_unstructured_header_mismatch_and_wrong_exhibit_are_not_imported(self):
        entry = IndexEntry('1-SA', 'Example', '123', '20261020', ENTRY.filename)
        for submission in (html_submission(entry).replace(b'0000000123\n', b'0000000456\n'),
                           html_submission(entry).replace(b'<TYPE>1-SA', b'<TYPE>EX-99')):
            client = Mock()
            client.get_bytes.side_effect = [http_error(404), submission]
            with self.assertRaises(UnsupportedDocument): primary_document(client, entry)

    def test_original_sec_html_and_text_submissions(self):
        folder = Path(__file__).parent / 'fixtures/sec_ingestion'
        sources = json.loads((folder / 'sources.json').read_text())
        for filename, cik, acc, form, day in (
            ('withdrawal.txt', '1827424', '0001827424-23-000011', '1-A-W', '20231205'),
            ('current-report.txt', '1981779', '0001062993-26-004190', '1-U', '20260811'),
        ):
            body = (folder / filename).read_bytes()
            self.assertEqual(hashlib.sha256(body).hexdigest(), sources[filename]['sha256'])
            client = Mock(); client.get_bytes.side_effect = [http_error(404), body]
            entry = IndexEntry(form, 'C3 Bullion, Inc.', cik, day, f'edgar/data/{cik}/{acc}.txt')
            parsed = Form1APipeline(client=client)._fetch_and_parse(entry)
            self.assertTrue(parsed.metadata_only)
            self.assertEqual(parsed.issuer.cik, cik)
            self.assertIsNone(parsed.total_offering_amount)
            self.assertEqual(parsed.raw_xml, '')

    def test_cf_primary_xml_fallback_keeps_source_and_zero(self):
        entry = IndexEntry('C-W', 'Example', '123', '20261020', ENTRY.filename)
        body = b'<edgarSubmission><headerData><filerInfo><filer><filerCredentials><cik>123</cik></filerCredentials></filer></filerInfo></headerData><formData><offeringInformation><price>0</price></offeringInformation></formData></edgarSubmission>'
        client = FakeSEC(entry)
        def fetch(path):
            if path.endswith('.idx'): return index_bytes(entry)
            if path.endswith('.xml'): raise http_error(404)
            return b'<DOCUMENT><TYPE>C-W\n<TEXT><XML>'+body+b'</XML></TEXT></DOCUMENT>'
        client.get_bytes = Mock(side_effect=fetch)
        stats = FormCPipeline(client=client).run(DAY, DAY)
        self.assertEqual(stats['upserted'], 1)
        filing = FormCPipeline.filing_model.objects.get()
        self.assertEqual(filing.price_per_security, 0)
        self.assertEqual(filing.raw_xml.encode(), body)


class NotificationProbeTests(SimpleTestCase):
    @patch.dict("os.environ", {"INGESTION_NOTIFICATION_TEST": "1"})
    def test_service_notification_probe_fails_without_database_access(self):
        with self.assertRaisesRegex(CommandError, "NOTIFICATION TEST ONLY"):
            call_command("check_ingestion_freshness", stdout=StringIO())

    def test_notification_probe_fails_without_database_access(self):
        with self.assertRaisesRegex(CommandError, 'NOTIFICATION TEST ONLY'):
            call_command('check_ingestion_freshness', notification_test=True, stdout=StringIO())


class MonitoringTests(TestCase):
    def healthy_state(self, now):
        for dataset in ('d', 'c', 'a'):
            IngestionRun.objects.create(dataset=dataset, start_date=DAY, end_date=DAY, finished_at=now, stats={'errors':0})
            IngestionJob.objects.create(dataset=dataset, kind='index', key=str(DAY), source_date=DAY,
                state='succeeded', last_success_at=now, outcome='indexed')

    def test_no_runs_is_unhealthy_and_adv_not_falsely_certified(self):
        report = freshness_report()
        self.assertFalse(report['healthy'])
        self.assertEqual(report['adv']['coverage_status'], 'refresh_not_instrumented')
        with self.assertRaises(CommandError): call_command('check_ingestion_freshness', stdout=StringIO())

    def test_empty_successful_indexes_are_fresh_but_stopped_scheduler_is_not(self):
        now = timezone.make_aware(__import__('datetime').datetime(2026,10,21,15))
        self.healthy_state(now)
        self.assertTrue(freshness_report(now=now)['healthy'])
        self.assertFalse(freshness_report(now=now+timedelta(hours=37))['healthy'])

    def test_recent_heartbeat_cannot_hide_old_missing_day_or_held_filing(self):
        now = timezone.make_aware(__import__('datetime').datetime(2026,10,21,15))
        self.healthy_state(now)
        IngestionJob.objects.create(dataset='a', kind='filing', key=ACC, source_date=DAY,
            state='held', created_at=now-timedelta(days=2), last_error='unsupported')
        report = freshness_report(now=now)
        self.assertFalse(report['healthy'])
        self.assertIn('held_jobs', report['datasets']['a']['issues'])
        self.assertIn('aged_backlog', report['datasets']['a']['issues'])

    def test_orchestrator_continues_other_datasets_after_failure(self):
        with patch.object(IngestPipeline, 'run', side_effect=RuntimeError('broken')), \
             patch.object(FormCPipeline, 'run', return_value={'errors':0}) as cf, \
             patch.object(Form1APipeline, 'run', return_value={'errors':0}) as rega:
            out = StringIO()
            with self.assertRaises(CommandError): call_command('ingest_edgar', stdout=out)
            cf.assert_called_once(); rega.assert_called_once()
            self.assertEqual(json.loads(out.getvalue())['d']['errors'], 1)


class PostgreSQLLeaseTests(TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_two_workers_only_one_claims_same_accession(self):
        job = IngestionJob.objects.create(dataset='d', kind='filing', key=ACC, source_date=DAY)
        barrier = Barrier(2)
        def worker():
            try:
                connections.close_all()
                barrier.wait(timeout=10)
                return claim(job.pk)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            tokens = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(sum(token is not None for token in tokens), 1)
        job.refresh_from_db(); self.assertEqual(job.attempts, 1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_global_advisory_lock_prevents_parallel_sec_workers(self):
        started = Event(); release = Event()
        def worker():
            try:
                connections.close_all()
                with patch('filings.ingest.reliability._run_pipeline', side_effect=lambda *a, **k: (started.set(), release.wait(10))):
                    IngestPipeline(client=FakeSEC()).run(DAY, DAY)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker)
            try:
                self.assertTrue(started.wait(10))
                with self.assertRaisesRegex(RuntimeError, 'worker is active'):
                    IngestPipeline(client=FakeSEC()).run(DAY, DAY)
            finally:
                release.set()
            future.result(timeout=10)
