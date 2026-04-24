from pathlib import Path

from django.test import SimpleTestCase

from filings.ingest.xml_parser import parse_primary_doc

FIXTURE = Path(__file__).parent / "fixtures" / "sample_primary_doc.xml"


class ParseXmlTests(SimpleTestCase):
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
