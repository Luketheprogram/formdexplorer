import csv
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from openpyxl import load_workbook

from accounts.models import ExportToken
from filings.exports import csv_safe_cell, xlsx_response
from filings.models import Filing, Issuer


class ExportSafetyTests(TestCase):
    paths = ("/export/csv/", "/export/xlsx/", "/cf/export/xlsx/", "/1a/export/xlsx/", "/adv/export/xlsx/")

    def setUp(self):
        self.user = get_user_model().objects.create_user(email="exports@example.com")
        self.client.force_login(self.user)

    def test_unpaid_tier_cannot_export_any_dataset(self):
        self.user.subscription_tier = "pro"
        self.user.subscription_status = "unpaid"
        self.user.save()
        for path in self.paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertRedirects(response, "/pricing/", fetch_redirect_response=False)

    def test_each_export_claims_credit_and_stale_claim_never_returns_file(self):
        for path in self.paths:
            with self.subTest(path=path):
                token = ExportToken.objects.create(user=self.user)
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Cache-Control"], "private, no-store")
                self.assertFalse(token.consume())
                token = ExportToken.objects.create(user=self.user)
                with patch.object(ExportToken, "consume", return_value=False):
                    response = self.client.get(path)
                self.assertEqual(response.status_code, 409)
                self.assertNotIn("Content-Disposition", response)
                token.delete()

    def test_failed_generation_preserves_credit(self):
        token = ExportToken.objects.create(user=self.user)
        with patch("filings.exports.xlsx_response", side_effect=RuntimeError("generation failed")):
            with self.assertRaises(RuntimeError):
                self.client.get("/export/xlsx/")
        token.refresh_from_db()
        self.assertTrue(token.is_unused)

    def test_xlsx_text_is_not_formula_and_numeric_types_survive(self):
        values = ["=1+1", "+SUM(1,2)", "@SUM(A1)", "-1+2", "\t=1+1", "#REF!", 0, -123, Decimal("0.25"), None]
        response = xlsx_response("test.xlsx", [values], [str(i) for i in range(len(values))])
        cells = list(load_workbook(BytesIO(response.content)).active[2])
        for cell, value in zip(cells, values):
            self.assertEqual(cell.value, value)
            self.assertNotEqual(cell.data_type, "f")
            if isinstance(value, str):
                self.assertEqual(cell.data_type, "s")

    def test_csv_neutralizes_source_text_and_preserves_zero_and_negative_numbers(self):
        for value in ("=1+1", " +1", "-1+2", "@SUM(A1)", "\ttext", "\n=1"):
            self.assertEqual(csv_safe_cell(value), "'" + value)
        self.assertEqual(csv_safe_cell(-123), -123)
        self.assertEqual(csv_safe_cell(0), 0)
        issuer = Issuer.objects.create(cik="123", name="=1+1")
        Filing.objects.create(issuer=issuer, accession_number="test", filing_date=date(2026, 1, 1), total_amount_sold=0)
        ExportToken.objects.create(user=self.user)
        rows = list(csv.reader(StringIO(self.client.get("/export/csv/").content.decode())))
        self.assertEqual(rows[1][3], "'=1+1")
        self.assertEqual(rows[1][8], "0")


class ConcurrentExportCreditTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_two_connections_cannot_consume_the_same_credit(self):
        user = get_user_model().objects.create_user(email="race@example.com")
        token = ExportToken.objects.create(user=user)
        barrier = Barrier(2)

        def consume():
            try:
                stale = ExportToken.objects.get(pk=token.pk)
                barrier.wait(timeout=10)
                return stale.consume()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: consume(), range(2)))
        self.assertEqual(sorted(results), [False, True])

    @skipUnlessDBFeature('has_select_for_update')
    def test_simultaneous_downloads_return_only_one_file_per_credit(self):
        from django.test import Client
        user = get_user_model().objects.create_user(email='download-race@example.com')
        clients = [Client(), Client()]
        for client in clients:
            client.force_login(user)
        consume = ExportToken.consume
        for path in ExportSafetyTests.paths:
            with self.subTest(path=path):
                token = ExportToken.objects.create(user=user)
                barrier = Barrier(2)

                def claim(stale):
                    barrier.wait(timeout=10)
                    return consume(stale)

                def download(client):
                    try:
                        response = client.get(path)
                        return response.status_code, response.has_header('Content-Disposition')
                    finally:
                        connections.close_all()

                with patch.object(ExportToken, 'consume', claim):
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        results = list(pool.map(download, clients))
                self.assertEqual(sorted(results), [(200, True), (409, False)])
                token.refresh_from_db()
                self.assertFalse(token.is_unused)
