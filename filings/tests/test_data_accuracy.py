import json
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from requests import HTTPError, Response

from crowdfunding.ingest.xml_parser import parse_form_c
from filings.ingest.index_parser import IndexEntry
from filings.ingest.issuers import upsert_issuer
from filings.ingest.pipeline import IngestPipeline
from filings.ingest.xml_parser import ParsedIssuer, parse_primary_doc
from filings.models import Filing, Issuer
from rega.ingest.documents import primary_xml, UnsupportedDocument
from rega.ingest.pipeline import Form1APipeline
from rega.ingest.xml_parser import parse_form_1a


D_XML = b'''<edgarSubmission><submissionType>D/A</submissionType>
<primaryIssuer><cik>0000000123</cik><entityName>Example</entityName></primaryIssuer>
<offeringData><salesCommissionsFindersFees><salesCommissions>0</salesCommissions><findersFees>0</findersFees>
</salesCommissionsFindersFees><salesCommissionsAmount>999</salesCommissionsAmount>
<offeringSalesAmounts><totalOfferingAmount>9007199254740993</totalOfferingAmount></offeringSalesAmounts>
</offeringData></edgarSubmission>'''


class ParserAccuracyTests(SimpleTestCase):
    def test_live_form_d_nested_dollar_amounts_and_investor_count(self):
        # Current SEC structure observed in accession 0000950138-26-000034.
        parsed = parse_primary_doc(b'''<edgarSubmission><offeringData>
        <investors><totalNumberAlreadyInvested>10</totalNumberAlreadyInvested></investors>
        <salesCommissionsFindersFees><salesCommissions><dollarAmount>0</dollarAmount></salesCommissions>
        <findersFees><dollarAmount>0</dollarAmount></findersFees></salesCommissionsFindersFees>
        </offeringData></edgarSubmission>''', "test")
        self.assertEqual(parsed.sales_commission, 0)
        self.assertEqual(parsed.finders_fees, 0)
        self.assertEqual(parsed.num_investors, 10)

    def test_form_d_preserves_zero_and_large_integer_precision(self):
        parsed = parse_primary_doc(D_XML, "test")
        self.assertEqual(parsed.sales_commission, 0)
        self.assertEqual(parsed.finders_fees, 0)
        self.assertEqual(parsed.total_offering_amount, 9007199254740993)

    def test_form_c_preserves_false_and_zero_before_fallbacks(self):
        parsed = parse_form_c(b'''<edgarSubmission><formData><offeringInformation>
        <targetOfferingAmount>0</targetOfferingAmount><offeringAmount>100</offeringAmount>
        <price>0</price><pricePerSecurity>2</pricePerSecurity>
        <overSubscriptionAccepted>false</overSubscriptionAccepted><oversubscriptionAccepted>true</oversubscriptionAccepted>
        </offeringInformation><totalAssetMostRecentFiscalYear>0</totalAssetMostRecentFiscalYear><totalAsset>50</totalAsset>
        </formData></edgarSubmission>''', "test")
        self.assertEqual(parsed.target_offering_amount, 0)
        self.assertEqual(parsed.price_per_security, 0)
        self.assertIs(parsed.oversubscription_accepted, False)
        self.assertEqual(parsed.total_assets, 0)

    def test_current_rega_schema_identity_address_and_financials(self):
        # Reduced structural fixture from SEC accession 0001342916-26-000064.
        parsed = parse_form_1a(b'''<edgarSubmission xmlns="http://www.sec.gov/edgar/rega/oneafiler">
        <headerData><submissionType>1-A/A</submissionType><issuerCredentials><cik>0001342916</cik></issuerCredentials></headerData>
        <formData><employeesInfo><issuerName>HNO International, Inc.</issuerName>
        <jurisdictionOrganization>NV</jurisdictionOrganization><yearIncorporation>2005</yearIncorporation></employeesInfo>
        <issuerInfo><street1>Example street</street1><city>MURRIETA</city><stateOrCountry>CA</stateOrCountry>
        <zipCode>92562</zipCode><phoneNumber>555-0100</phoneNumber><cashEquivalents>0</cashEquivalents>
        <totalAssets>0</totalAssets></issuerInfo><summaryInfo><indicateTier1Tier2Offering>Tier2</indicateTier1Tier2Offering>
        <securitiesOfferedTypes>Equity</securitiesOfferedTypes><pricePerSecurity>0</pricePerSecurity></summaryInfo>
        </formData></edgarSubmission>''', "test")
        self.assertEqual(parsed.issuer.name, "HNO International, Inc.")
        self.assertEqual(parsed.issuer.cik, "1342916")
        self.assertEqual(parsed.issuer.state, "CA")
        self.assertEqual(parsed.issuer.year_of_incorporation, "2005")
        self.assertEqual(parsed.cash_equivalents, 0)
        self.assertEqual(parsed.total_assets, 0)
        self.assertEqual(parsed.tier, "Tier 2")
        self.assertTrue(parsed.is_amendment)

    def test_rega_fallback_uses_primary_type_not_exhibit(self):
        client = Mock()
        response = Response(); response.status_code = 404
        submission = b'''<DOCUMENT><TYPE>EX-99\n<TEXT><XML><wrong/></XML></TEXT></DOCUMENT>
        <DOCUMENT><TYPE>1-A/A\n<TEXT><XML><edgarSubmission/></XML></TEXT></DOCUMENT>'''
        def fetch(path):
            if path.endswith("primary_doc.xml"):
                raise HTTPError(response=response)
            return submission
        client.get_bytes.side_effect = fetch
        entry = IndexEntry("1-A/A", "Example", "123", "2026-01-01", "edgar/data/123/0000000123-26-000001.txt")
        self.assertEqual(primary_xml(client, entry), b"<edgarSubmission/>")
        submission = b'<DOCUMENT><TYPE>1-A/A\n<TEXT><html>Unstructured</html></TEXT></DOCUMENT>'
        with self.assertRaises(UnsupportedDocument):
            primary_xml(client, entry)
        response.status_code = 403
        with self.assertRaises(HTTPError):
            primary_xml(client, entry)


class IngestionFailureTests(TestCase):
    def test_failed_download_counts_as_error_not_success(self):
        client = Mock(); client.get_bytes.side_effect = RuntimeError("download failed")
        pipeline = IngestPipeline(client=client)
        pipeline._fetch_day_index = Mock(return_value=[IndexEntry("D", "Example", "123", "2026-01-01", "edgar/data/123/0000000123-26-000001.txt")])
        with self.assertLogs("filings.ingest.reliability", level="ERROR"):
            stats = pipeline.run(date(2026, 1, 1), date(2026, 1, 1))
        self.assertEqual(stats["errors"], 1)
        self.assertEqual(stats["upserted"], 0)


class IssuerAndRepairTests(TestCase):
    def setUp(self):
        self.issuer = Issuer.objects.create(cik="123", name="Current name", name_slug="stable-url", state="CA")
        self.filing = Filing.objects.create(issuer=self.issuer, accession_number="test", filing_date=date(2026, 5, 1), raw_xml=D_XML.decode())

    def test_new_issuer_name_is_bounded_before_first_insert(self):
        issuer = upsert_issuer(ParsedIssuer(cik="456", name="Long issuer " * 30), date(2026, 1, 1))
        self.assertEqual(len(issuer.name), 255)
        self.assertLessEqual(len(issuer.name_slug), 255)

    def test_old_or_blank_import_cannot_replace_known_identity_or_url(self):
        old = ParsedIssuer(cik="0000000123", name="Old name", state="NY", phone="555-0100")
        issuer = upsert_issuer(old, date(2025, 1, 1))
        self.assertEqual(issuer.name, "Current name")
        self.assertEqual(issuer.state, "CA")
        self.assertEqual(issuer.phone, "555-0100")
        issuer = upsert_issuer(ParsedIssuer(cik="123", name="CIK 123"), date(2026, 6, 1))
        self.assertEqual(issuer.name, "Current name")
        self.assertEqual(issuer.state, "CA")
        issuer = upsert_issuer(ParsedIssuer(cik="123", name="Renamed issuer"), date(2026, 7, 1))
        self.assertEqual(issuer.name, "Renamed issuer")
        self.assertEqual(issuer.name_slug, "stable-url")

    def test_dry_run_is_default_and_apply_is_journaled_idempotent_and_filing_only(self):
        out = StringIO()
        call_command("repair_filing_data", dataset="d", stdout=out)
        self.filing.refresh_from_db()
        self.assertEqual(self.filing.form_type, "D")
        self.assertIn('"form_type": "D/A"', out.getvalue())
        with self.assertRaises(CommandError):
            call_command("repair_filing_data", dataset="d", apply=True)
        with TemporaryDirectory() as folder:
            journal = str(Path(folder) / "repair.jsonl")
            call_command("repair_filing_data", dataset="d", apply=True, journal=journal, stdout=StringIO())
            rows = [json.loads(line) for line in Path(journal).read_text().splitlines()]
            self.assertEqual(rows[0]["before"]["form_type"], "D")
            self.assertEqual(rows[1]["state"], "committed")
            with self.assertRaises(CommandError):
                call_command("repair_filing_data", dataset="d", apply=True, journal=journal)
        self.filing.refresh_from_db(); self.issuer.refresh_from_db()
        self.assertEqual(self.filing.form_type, "D/A")
        self.assertTrue(self.filing.is_amendment)
        self.assertEqual(self.filing.sales_commission, 0)
        self.assertEqual(self.issuer.name, "Current name")
        self.assertEqual(self.issuer.name_slug, "stable-url")
        out = StringIO()
        call_command("repair_filing_data", dataset="d", stdout=out)
        self.assertIn('"changed": 0', out.getvalue())

    def test_repair_will_not_guess_original_when_xml_omits_type(self):
        self.filing.form_type = "D/A"; self.filing.is_amendment = True
        self.filing.raw_xml = '<edgarSubmission><primaryIssuer><cik>123</cik></primaryIssuer></edgarSubmission>'
        self.filing.save()
        out = StringIO(); call_command("repair_filing_data", dataset="d", stdout=out)
        self.assertIn('"changed": 0', out.getvalue())

    def test_malformed_source_does_not_abort_repair_batch(self):
        self.filing.raw_xml = D_XML.decode().replace('</edgarSubmission>', '')
        self.filing.save()
        Filing.objects.create(issuer=self.issuer, accession_number='good-after-bad',
                              filing_date=date(2026, 5, 2), raw_xml=D_XML.decode())
        out = StringIO()
        call_command('repair_filing_data', dataset='d', stdout=out)
        self.assertIn('"skipped": 1', out.getvalue())
        self.assertIn('"changed": 1', out.getvalue())
