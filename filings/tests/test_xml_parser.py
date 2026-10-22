from pathlib import Path
from unittest.mock import Mock

from django.test import SimpleTestCase

from filings.ingest.xml_parser import parse_primary_doc
from filings.ingest.pipeline import IngestPipeline
from filings.ingest.index_parser import IndexEntry

FIXTURE = Path(__file__).parent / "fixtures" / "sample_primary_doc.xml"


class ParseXmlTests(SimpleTestCase):
    def test_root_submission_type_is_an_amendment(self):
        parsed = parse_primary_doc(b'<edgarSubmission><submissionType>D/A</submissionType></edgarSubmission>', 'test')
        self.assertEqual(parsed.form_type, 'D/A')
        self.assertTrue(parsed.is_amendment)

    def test_index_submission_type_overrides_missing_xml_default(self):
        client = Mock()
        client.get_bytes.return_value = b'<edgarSubmission><primaryIssuer><cik>1234</cik></primaryIssuer></edgarSubmission>'
        pipeline = IngestPipeline(client=client)
        for form_type in ['D', 'D/A']:
            entry = IndexEntry(form_type, 'Example', '1234', '2026-10-21', 'edgar/data/1234/0001234567-26-000001.txt')
            parsed = pipeline._fetch_and_parse(entry)
            self.assertEqual(parsed.form_type, form_type)
            self.assertEqual(parsed.is_amendment, form_type == 'D/A')

    def test_parses_basic_fields(self):
        pf = parse_primary_doc(FIXTURE.read_bytes(), "0001234567-26-000001")
        self.assertEqual(pf.accession_number, "0001234567-26-000001")
        self.assertEqual(pf.form_type, "D")
        self.assertFalse(pf.is_amendment)
        self.assertEqual(pf.issuer.name, "Acme Ventures Fund III LP")
        self.assertEqual(pf.issuer.state, "CA")
        self.assertEqual(pf.industry_group, "Pooled Investment Fund")
        self.assertEqual(pf.total_offering_amount, 50000000)
        self.assertEqual(pf.total_amount_sold, 12500000)
        self.assertEqual(pf.minimum_investment, 250000)
        self.assertEqual(pf.num_investors, 18)
        self.assertIn("06b", pf.offering_type)
