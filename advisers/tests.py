from django.test import TestCase, override_settings

from .models import Adviser


@override_settings(DEBUG=True, SITE_URL='https://formdexplorer.com', SEO_INDEXING_ENABLED=True)
class AdviserIdentifierTests(TestCase):
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
