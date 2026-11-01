import json
from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from lxml import html

from content.models import Article
from content.reviewed_guides import ARTICLES
from filings.intelligence import activity_report, build_report, filing_changes, month_offset, monthly_activity, percent
from filings.models import Filing, Issuer


@override_settings(SITE_URL="https://formdexplorer.com", SEO_INDEXING_ENABLED=True, DEBUG=True)
class IntelligenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Issuer.objects.create(cik="1001", name="Source research LP", state="CA")
        cls.b = Issuer.objects.create(cik="1002", name="Other legal issuer LP", state="NY")
        cls.blank = Issuer.objects.create(cik="1003", name="  ", state="TX")
        cls.today = date(2026, 11, 1)
        cls.initial = Filing.objects.create(issuer=cls.a, accession_number="0000001001-26-000001", filing_date=date(2026, 9, 1),
            industry_group="Biotechnology", total_offering_amount=10000000, total_amount_sold=2000000, num_investors=10, raw_xml="x"*10000)
        cls.amended = Filing.objects.create(issuer=cls.a, accession_number="0000001001-26-000002", filing_date=date(2026, 10, 1),
            industry_group="Biotechnology", form_type="D/A", is_amendment=True, total_offering_amount=10000000,
            total_amount_sold=3000000, num_investors=0, raw_xml="x"*10000)
        cls.missing = Filing.objects.create(issuer=cls.b, accession_number="0000001002-26-000001", filing_date=date(2026, 10, 2),
            industry_group="Other Technology", total_offering_amount=None, total_amount_sold=0, num_investors=None)

    def setUp(self):
        cache.clear()

    def test_month_boundaries_include_twelve_and_handle_year_and_leap_year(self):
        self.assertEqual(month_offset(date(2026, 1, 31), -1), date(2025, 12, 1))
        self.assertEqual(month_offset(date(2024, 3, 31), -1), date(2024, 2, 1))
        with self.assertNumQueries(1):
            rows = monthly_activity(Filing.objects.all(), today=self.today)
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[0]["month"], date(2025, 12, 1))
        self.assertTrue(rows[-1]["partial"])
        self.assertEqual(rows[-1]["filings"], 0)
        self.assertFalse(rows[-2]["partial"])

    def test_period_comparison_excludes_partial_current_month_and_future(self):
        Filing.objects.create(issuer=self.a, accession_number="partial", filing_date=self.today)
        Filing.objects.create(issuer=self.a, accession_number="future", filing_date=date(2026, 11, 2))
        with self.assertNumQueries(2):
            report = build_report(Filing.objects.all(), today=self.today)
        self.assertEqual(report["current"]["month"], date(2026, 10, 1))
        self.assertEqual(report["current"]["filings"], 2)
        self.assertEqual(report["previous"]["filings"], 1)
        self.assertEqual(report["delta"], 1)
        self.assertEqual(report["change_percent"], Decimal("100.0"))
        self.assertEqual(report["stats"]["filings"], 4)
        self.assertEqual(report["months"][-1]["filings"], 1)
        self.assertNotIn("total_raised", report["stats"])

    def test_missing_values_zero_invalid_negatives_and_amendment_flags(self):
        Filing.objects.create(issuer=self.a, accession_number="flag-only", filing_date=date(2026, 10, 3),
            form_type="D", is_amendment=True, total_amount_sold=-1)
        Filing.objects.create(issuer=self.a, accession_number="type-only", filing_date=date(2026, 10, 4), form_type="D/A")
        report = build_report(Filing.objects.all(), today=self.today)
        self.assertEqual(report["stats"]["amendments"], 3)
        self.assertEqual(report["stats"]["sold_known"], 3)  # includes reported zero
        self.assertEqual(report["sold_missing"], 2)
        self.assertEqual(report["current"]["amendments"], 3)
        self.assertEqual(report["current"]["originals"], 1)

    def test_distinct_issuer_counts_not_summed_across_months(self):
        report = build_report(Filing.objects.all(), today=self.today)
        self.assertEqual(report["stats"]["issuers"], 2)
        self.assertEqual(sum(r["issuers"] for r in report["months"]), 3)
        self.assertEqual(report["amendment_share"], Decimal("33.3"))

    def test_empty_and_zero_denominator_do_not_invent_growth(self):
        report = build_report(Filing.objects.none(), today=self.today)
        self.assertIsNone(report["change_percent"])
        self.assertIsNone(report["amendment_share"])
        self.assertIsNone(report["latest_age_days"])
        self.assertEqual(percent(0, 2), 0)
        self.assertIsNone(percent(1, 0))

    def test_aggregation_handles_duplicate_join_rows_without_inflation(self):
        from filings.models import RelatedPerson
        for name in ["A", "B"]:
            RelatedPerson.objects.create(filing=self.initial, name=name)
        report = build_report(Filing.objects.filter(related_persons__isnull=False), today=self.today)
        self.assertEqual(report["stats"]["filings"], 1)
        self.assertEqual(report["months"][-3]["filings"], 1)

    def test_public_cache_is_scoped_and_never_selects_xml(self):
        with CaptureQueriesContext(connection) as queries:
            ca = activity_report(state="CA")
        self.assertEqual(len(queries), 2)
        self.assertFalse(any('"raw_xml"' in q["sql"] for q in queries))
        with self.assertNumQueries(0):
            self.assertEqual(activity_report(state="CA"), ca)
        self.assertEqual(activity_report(state="NY")["stats"]["filings"], 1)
        self.assertEqual(activity_report(industry="biotechnology")["stats"]["filings"], 2)
        Filing.objects.create(issuer=self.blank, accession_number="blank", filing_date=date(2026, 10, 1))
        self.assertEqual(activity_report()["stats"]["filings"], 3)

    def test_differences_are_not_sums_and_zero_investor_count_is_preserved(self):
        result = filing_changes(self.initial, self.amended)
        rows = {r["field"]: r for r in result["rows"]}
        self.assertEqual(rows["total_amount_sold"]["delta"], 1000000)
        self.assertEqual(rows["total_offering_amount"]["delta"], 0)
        self.assertEqual(rows["num_investors"]["later"], 0)
        self.assertEqual(rows["num_investors"]["delta"], -10)
        self.assertIsNone(rows["minimum_investment"]["delta"])

    def test_cross_issuer_same_accession_reversed_and_same_day_safeguards(self):
        for before, after in [(self.initial, self.missing), (self.initial, self.initial), (self.amended, self.initial)]:
            with self.assertRaises(ValueError):
                filing_changes(before, after)
        self.amended.filing_date = self.initial.filing_date
        result = filing_changes(self.initial, self.amended)
        self.assertTrue(result["same_day"])
        self.assertTrue(all(r["delta"] is None for r in result["rows"]))

    def test_missing_or_negative_values_cannot_be_used_as_zero(self):
        self.amended.total_amount_sold = None
        self.amended.num_investors = -1
        result = filing_changes(self.initial, self.amended)
        self.assertIsNone(result["rows"][1]["delta"])
        self.assertIsNone(result["rows"][2]["later"])

    def test_public_reports_canonical_crawlable_and_without_ad_slots(self):
        for path in ["/research/", "/research/filing-activity/", "/research/amendments/", "/research/coverage/", "/about/", "/editorial/"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("X-Robots-Tag", response)
                doc = html.fromstring(response.content)
                self.assertEqual(len(doc.xpath("//h1")), 1)
                self.assertEqual(doc.xpath('//link[@rel="canonical"]/@href'), ["https://formdexplorer.com" + path])
                self.assertNotContains(response, "data-ad-slot=")
                self.assertContains(response, "Skip to content")
                graph = json.loads(doc.xpath('//script[@type="application/ld+json"]/text()')[0])
                self.assertNotIn("Dataset", str(graph))  # don't invent a downloadable dataset
                self.assertContains(self.client.get("/sitemap-static.xml"), "https://formdexplorer.com" + path)

    def test_empty_reports_noindex_preserve_functionality_and_coverage_definitions(self):
        Filing.objects.all().delete()
        for path in ["/research/", "/research/filing-activity/", "/research/amendments/"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["X-Robots-Tag"], "noindex, follow")
            self.assertNotContains(self.client.get("/sitemap-static.xml"), "<loc>https://formdexplorer.com" + path + "</loc>")
        self.assertContains(self.client.get("/research/coverage/"), "No eligible Form D records")

    def test_category_comparison_validates_choices_and_has_consistent_periods(self):
        response = self.client.get("/research/compare/?kind=state&left=CA&right=NY")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Robots-Tag"], "noindex, follow")
        self.assertEqual(len(response.context["comparisons"]), 2)
        self.assertEqual(len(response.context["comparison_months"]), 12)
        self.assertEqual(response.context["comparisons"][0]["report"]["current"]["month"], response.context["comparisons"][1]["report"]["current"]["month"])
        self.assertContains(response, "current stored business address")
        for suffix in ["kind=bad", "kind=state&left=ZZ&right=NY", "kind=industry&left=biotechnology&right=biotechnology"]:
            self.assertEqual(self.client.get("/research/compare/?" + suffix).status_code, 400)
        self.assertEqual(self.client.get("/research/compare/?kind=industry&left=biotechnology&right=other-technology").status_code, 200)

    def test_change_viewer_enforces_issuer_and_accession_boundaries(self):
        response = self.client.get("/research/filing-changes/?cik=1001")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Robots-Tag"], "noindex, follow")
        self.assertContains(response, "Same issuer CIK; offering identity has not been established")
        self.assertContains(response, self.initial.edgar_url)
        self.assertContains(response, "$1,000,000")
        self.assertEqual(self.client.get("/research/filing-changes/?cik=1001&earlier="+self.missing.accession_number).status_code, 400)
        self.assertEqual(self.client.get("/research/filing-changes/?cik=bad").status_code, 400)
        self.assertEqual(self.client.get("/research/filing-changes/?cik=9999").status_code, 404)
        self.assertContains(self.client.get("/research/filing-changes/?cik=1002"), "At least two stored filings")
        self.assertEqual(self.client.get("/research/not-a-report/").status_code, 404)

    def test_single_populated_category_has_a_useful_successful_empty_state(self):
        Filing.objects.filter(issuer=self.b).delete()
        response = self.client.get("/research/compare/?kind=state&left=CA")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Two populated categories are needed")

    def test_issuer_enriched_without_loading_xml_or_losing_filings(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(f"/issuer/{self.a.url_slug}/")
        self.assertContains(response, "Differences between reported disclosures")
        self.assertContains(response, self.initial.accession_number)
        self.assertContains(response, self.amended.accession_number)
        self.assertNotContains(response, "$5,000,000")
        self.assertFalse(any('"raw_xml"' in q["sql"] for q in queries))

    def test_category_sitemaps_exclude_only_blank_name_categories(self):
        Filing.objects.create(issuer=self.blank, accession_number="blank", filing_date=self.today, industry_group="Coal Mining")
        self.assertNotContains(self.client.get("/sitemap-states.xml"), "/state/TX/")
        self.assertNotContains(self.client.get("/sitemap-industries.xml"), "/industry/coal-mining/")
        self.assertContains(self.client.get("/sitemap-states.xml"), "/state/CA/")
        self.assertEqual(self.client.get("/state/TX/")["X-Robots-Tag"], "noindex, follow")
        self.assertEqual(self.client.get("/industry/coal-mining/")["X-Robots-Tag"], "noindex, follow")

    def test_category_dataset_share_uses_same_month_not_lifetime_counts(self):
        from filings.intelligence import category_report
        with patch("filings.intelligence.timezone.localdate", return_value=self.today):
            report = category_report(state="CA")
        self.assertEqual(report["dataset_filings"], 2)
        self.assertEqual(report["dataset_share"], Decimal("50.0"))

    def test_reviewed_guides_are_seeded_idempotently_and_have_primary_sources(self):
        call_command("seed_articles", stdout=StringIO())
        dates = {a.slug: (a.published_at, a.updated_at) for a in Article.objects.all()}
        call_command("seed_articles", stdout=StringIO())
        self.assertEqual(dates, {a.slug: (a.published_at, a.updated_at) for a in Article.objects.all()})
        for guide in ARTICLES:
            response = self.client.get(f'/learn/{guide["slug"]}/')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "https://www.sec.gov/" if "https://www.sec.gov/" in guide["body"] else "https://www.investor.gov/")
            self.assertContains(response, "Editorial standards and corrections")
            self.assertContains(response, "Updated")
            doc = html.fromstring(response.content)
            for url in set(doc.xpath('//article//a/@href')):
                if url.startswith("/"):
                    self.assertLess(self.client.get(url).status_code, 400, url)

    def test_readiness_commands_are_read_only_and_report_manual_steps(self):
        call_command("seed_articles", stdout=StringIO())
        before = (Filing.objects.count(), Issuer.objects.count(), Article.objects.count())
        out = StringIO()
        call_command("audit_adsense_readiness", stdout=out)
        data = json.loads(out.getvalue())
        self.assertEqual(data["assessment"], "LOCAL_CHECKS_ONLY")
        self.assertTrue(any(c["status"] == "manual" for c in data["checks"]))
        self.assertEqual(data["quality"]["missing_or_unpublished_guides"], [])
        self.assertEqual(data["quality"]["guides_differing_from_reviewed_source"], [])
        self.assertEqual(before, (Filing.objects.count(), Issuer.objects.count(), Article.objects.count()))
        out = StringIO()
        call_command("audit_content_quality", stdout=out)
        self.assertEqual(len(json.loads(out.getvalue())["routes"]), 7)
