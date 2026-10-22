from django.test import TestCase, override_settings

from .models import Adviser
from .disclosures import disciplinary_status
from .iapd import parse_firm


@override_settings(DEBUG=True, SITE_URL='https://formdexplorer.com', SEO_INDEXING_ENABLED=True)
class AdviserIdentifierTests(TestCase):
    def test_unknown_legacy_disclosures_are_not_presented_as_clean(self):
        Adviser.objects.create(crd="111", name="Unknown source", has_disciplinary=False)
        response = self.client.get("/adv/111/")
        self.assertContains(response, "Unknown — verify on SEC IAPD")
        self.assertNotContains(response, "None reported")

    def test_explicit_false_and_true_source_values(self):
        for value, expected in [(False, False), ("false", False), (True, True), ("yes", True), ("", None)]:
            with self.subTest(value=value):
                payload = {"basicInformation": {"firmId": "123", "hasDisclosure": value}}
                self.assertIs(disciplinary_status(payload), expected)
                self.assertEqual(parse_firm(payload)["has_disciplinary"], expected is True)
        self.assertIsNone(disciplinary_status({}))

    def test_inferred_matches_are_labeled(self):
        from filings.models import Issuer
        Adviser.objects.create(crd="222", name="Shared Brand Advisors")
        Issuer.objects.create(cik="222", name="Shared Brand Advisors")
        response = self.client.get("/adv/222/")
        self.assertContains(response, "Possible Form D name matches (not verified)")
        self.assertContains(response, "High name-match confidence")

    def test_bulk_import_sec_identifier_opens_but_is_not_indexed_or_labeled_crd(self):
        Adviser.objects.create(crd='801-78074', sec_file_number='801-78074', name='Legacy research fixture')
        response = self.client.get('/adv/801-78074/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Robots-Tag'], 'noindex, follow')
        self.assertContains(response, 'SEC file number 801-78074')
        self.assertNotContains(response, 'CRD 801-78074')
        self.assertNotContains(response, '/firm/summary/801-78074')
        self.assertContains(response, 'href="https://adviserinfo.sec.gov/"')
        search = self.client.get('/adv/')
        self.assertContains(search, 'href="/adv/801-78074/"')
        self.assertNotContains(search, 'CRD 801-78074')

    def test_numeric_crd_remains_indexable_and_links_to_specific_source(self):
        Adviser.objects.create(crd='123456', name='Verified format fixture')
        response = self.client.get('/adv/123456/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('X-Robots-Tag', response)
        self.assertContains(response, 'CRD 123456')
        self.assertContains(response, 'https://adviserinfo.sec.gov/firm/summary/123456')

    def test_unknown_or_malformed_identifiers_return_real_404(self):
        for identifier in ['801-99999', 'abc', '1e10']:
            self.assertEqual(self.client.get(f'/adv/{identifier}/').status_code, 404)
