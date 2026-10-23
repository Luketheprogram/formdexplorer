from datetime import date
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.http import QueryDict
from django.test import TestCase

from accounts.models import ExportToken
from api.models import ApiKey
from filings.models import Filing, Issuer, SavedSearch
from filings.search import build_filing_query
from filings.search_params import SearchValidationError


class SearchValidationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="search@example.com")
        for cik, state, industry in [("1", "CA", "Technology"), ("2", "NY", "Other"), ("3", "TX", "Other")]:
            issuer = Issuer.objects.create(cik=cik, name=f"Issuer {cik}", state=state)
            Filing.objects.create(issuer=issuer, accession_number=cik, filing_date=date(2026, 1, 1),
                                  total_offering_amount=1000000, industry_group=industry)

    def test_saved_and_interactive_multiselects_are_equivalent(self):
        query = QueryDict("state=CA&state=NY&industry=Technology&industry=Other&min_amount=1,000,000")
        saved = {k: query.getlist(k) if k in {"state", "industry"} else query[k] for k in query}
        self.assertEqual(list(build_filing_query(saved)), list(build_filing_query(query)))
        self.assertEqual(build_filing_query(saved).count(), 2)

    def test_invalid_filters_have_feedback_without_500_or_unfiltered_results(self):
        for params in [{"date_from": "not-a-date"}, {"date_from": "2026-02-30"},
                       {"min_amount": "1e100"}, {"min_amount": "9" * 100},
                       {"min_amount": "-1"}, {"min_sold": "oops"},
                       {"min_amount": "20", "max_amount": "10"},
                       {"date_from": "2026-01-02", "date_to": "2026-01-01"}]:
            for path in ["/search/", "/search/partial/", "/cf/", "/cf/search/partial/", "/1a/", "/1a/search/partial/"]:
                with self.subTest(params=params, path=path):
                    response = self.client.get(path, params)
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, "Please correct these search filters")
                    self.assertEqual(response.context["total"], 0)

    def test_comma_formatted_amount_is_accepted_and_search_remains_noindex(self):
        response = self.client.get("/search/", {"min_amount": "1,000,000"})
        self.assertEqual(response.context["total"], 3)
        self.assertContains(response, 'content="noindex, follow"')

    def test_invalid_export_does_not_consume_credit(self):
        self.client.force_login(self.user)
        token = ExportToken.objects.create(user=self.user)
        for path in ["/export/csv/", "/export/xlsx/", "/cf/export/xlsx/", "/1a/export/xlsx/"]:
            response = self.client.get(path, {"min_amount": "bad"})
            self.assertEqual(response.status_code, 400)
            token.refresh_from_db()
            self.assertTrue(token.is_unused)

    def test_api_validation_and_unpaid_status(self):
        self.user.subscription_tier = "api"
        self.user.subscription_status = "active"
        self.user.save()
        _, raw = ApiKey.generate(self.user)
        response = self.client.get("/api/v1/filings/", {"date_from": "bad"}, HTTP_AUTHORIZATION=f"Bearer {raw}")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_filters")
        self.user.subscription_status = "unpaid"
        self.user.save()
        self.assertEqual(self.client.get("/api/v1/filings/", HTTP_AUTHORIZATION=f"Bearer {raw}").status_code, 403)

    def test_invalid_saved_search_does_not_abort_following_search(self):
        SavedSearch.objects.create(user=self.user, name="invalid", params={"date_from": "bad"})
        SavedSearch.objects.create(user=self.user, name="valid", params={"state": ["CA", "NY"]})
        out, err = StringIO(), StringIO()
        call_command("send_saved_search_alerts", dry_run=True, stdout=out, stderr=err)
        self.assertIn("invalid filters", err.getvalue())
        self.assertIn('"initialized": 1', out.getvalue())

    def test_nested_saved_values_are_rejected(self):
        with self.assertRaises(SearchValidationError):
            build_filing_query({"state": {"bad": "shape"}})

    def test_api_rejects_offset_outside_database_integer_range(self):
        self.user.subscription_tier = 'api'
        self.user.subscription_status = 'active'
        self.user.save()
        _, raw = ApiKey.generate(self.user)
        for offset in ('9' * 100, '9223372036854775807'):
            response = self.client.get('/api/v1/filings/', {'offset': offset},
                                       HTTP_AUTHORIZATION=f'Bearer {raw}')
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()['error'], 'bad_pagination')
