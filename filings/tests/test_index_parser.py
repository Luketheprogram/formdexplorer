from django.test import SimpleTestCase

from filings.ingest.index_parser import (
    accession_from_filename,
    parse_form_idx,
    primary_doc_url,
)

# Matches EDGAR's real form.idx layout: no leading space, YYYYMMDD date.
SAMPLE = """Description:           Daily Index of EDGAR Dissemination Feed by Form Type
Last Data Received:    Apr 21, 2026

Form Type   Company Name                                                  CIK         Date Filed  File Name
---------------------------------------------------------------------------------------------------------------------------------------------
1-A              Upstream Life Securities Fund I, LLC                          2126686     20260421    edgar/data/2126686/0002126686-26-000001.txt
D                ACME VENTURES FUND III LP                                     1234567     20260420    edgar/data/1234567/0001234567-26-000001.txt
D/A              OTHER FUND LP                                                 2222222     20260420    edgar/data/2222222/0002222222-26-000002.txt
10-K             SOMETHING ELSE INC                                            3333333     20260420    edgar/data/3333333/0003333333-26-000003.txt
"""


class IndexParserTests(SimpleTestCase):
    def test_filters_form_d_only(self):
        entries = parse_form_idx(SAMPLE)
        forms = {e.form_type for e in entries}
        self.assertEqual(forms, {"D", "D/A"})
        self.assertEqual(len(entries), 2)

    def test_primary_doc_url(self):
        url = primary_doc_url("edgar/data/1234567/0001234567-26-000001.txt")
        self.assertEqual(
            url,
            "/Archives/edgar/data/1234567/000123456726000001/primary_doc.xml",
        )

    def test_accession(self):
        self.assertEqual(
            accession_from_filename("edgar/data/1234567/0001234567-26-000001.txt"),
            "0001234567-26-000001",
        )
