import json
from datetime import date, timedelta
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from lxml import html

from content.models import Article
from content.research_guides import RESEARCH_GUIDES
from filings.models import Filing, Issuer
from filings.research import activity_stats, directory_data


@override_settings(SITE_URL="https://formdexplorer.com", SEO_INDEXING_ENABLED=True, DEBUG=True)
class ResearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.issuer = Issuer.objects.create(name="Research & Partners LP", cik="12345", state="CA")
        cls.other = Issuer.objects.create(name="Other issuer", cik="23456", state="TX")
        cls.empty = Issuer.objects.create(name="No filings", cik="34567", state="NY")
        today = timezone.localdate()
        cls.original = Filing.objects.create(issuer=cls.issuer, accession_number="original", filing_date=today-timedelta(days=20),
            industry_group="Biotechnology", total_offering_amount=10000000, total_amount_sold=2000000, raw_xml="x"*10000)
        cls.amended = Filing.objects.create(issuer=cls.issuer, accession_number="amended", filing_date=today,
            form_type="D/A", is_amendment=True, industry_group="Biotechnology", total_offering_amount=10000000,
            total_amount_sold=3000000, num_investors=0, raw_xml="x"*10000)
        Filing.objects.create(issuer=cls.other, accession_number="old", filing_date=today-timedelta(days=400),
            industry_group="biotechnology", total_offering_amount=50000000000, total_amount_sold=0)

    def setUp(self):
        cache.clear()

    def test_activity_counts_include_large_missing_and_amended_records_without_summing_money(self):
        with self.assertNumQueries(1):
            stats = activity_stats(Filing.objects.all())
        self.assertEqual(stats["total_filings"], 3)
        self.assertEqual(stats["issuer_count"], 2)
        self.assertEqual(stats["amendment_count"], 1)
        self.assertEqual(stats["original_count"], 2)
        self.assertEqual(stats["filings_last_year"], 2)
        self.assertNotIn("total_raised", stats)

    def test_form_type_alone_marks_amendment_and_future_is_not_in_last_year(self):
        Filing.objects.create(issuer=self.issuer, accession_number="future", filing_date=timezone.localdate()+timedelta(days=1), form_type="D/A")
        stats = activity_stats(Filing.objects.all())
        self.assertEqual(stats["amendment_count"], 2)
        self.assertEqual(stats["filings_last_year"], 2)

    def test_directory_is_data_backed_case_insensitive_and_cached_without_full_records(self):
        with CaptureQueriesContext(connection) as queries:
            data = directory_data()
        self.assertEqual(len(queries), 2)
        self.assertFalse(any('"raw_xml"' in q["sql"] for q in queries))
        self.assertEqual({r["code"] for r in data["states"]}, {"CA", "TX"})
        self.assertEqual(len(data["industries"]), 1)
        self.assertEqual(data["industries"][0]["filing_count"], 3)
        with self.assertNumQueries(0):
            self.assertEqual(directory_data(), data)

    def test_directory_cache_refresh_includes_new_ingested_category(self):
        self.assertNotIn("NY", {r["code"] for r in directory_data()["states"]})
        Filing.objects.create(issuer=self.empty, accession_number="new", filing_date=date.today(), industry_group="Investing")
        cache.delete("research:directories:v1")  # simulate expiry in each web process
        self.assertIn("NY", {r["code"] for r in directory_data()["states"]})

    def test_blank_issuer_and_unknown_categories_do_not_create_directory_links(self):
        blank = Issuer.objects.create(name="   ", cik="999", state="NY")
        Filing.objects.create(issuer=blank, accession_number="blank", filing_date=date.today(), industry_group="Coal Mining")
        for path in ["/states/", "/industries/"]:
            response = self.client.get(path)
            self.assertNotContains(response, '/state/NY/')
            self.assertNotContains(response, '/industry/coal-mining/')

    def test_directories_are_indexable_with_matching_breadcrumbs_and_sitemap(self):
        for path, child in [("/states/", "/state/CA/"), ("/industries/", "/industry/biotechnology/")]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("X-Robots-Tag", response)
            doc = html.fromstring(response.content)
            self.assertEqual(doc.xpath('//link[@rel="canonical"]/@href'), ["https://formdexplorer.com"+path])
            graph = json.loads(doc.xpath('//script[@type="application/ld+json"]/text()')[0])["@graph"]
            crumb = next(x for x in graph if x["@type"] == "BreadcrumbList")
            self.assertEqual(crumb["itemListElement"][-1]["item"], "https://formdexplorer.com"+path)
            self.assertContains(response, f'href="{child}"')
            self.assertContains(self.client.get("/sitemap-static.xml"), "https://formdexplorer.com"+path)

    def test_empty_directories_are_noindex_and_absent_from_sitemap(self):
        Filing.objects.all().delete()
        for path in ["/states/", "/industries/"]:
            self.assertEqual(self.client.get(path)["X-Robots-Tag"], "noindex, follow")
            self.assertNotContains(self.client.get("/sitemap-static.xml"), "https://formdexplorer.com"+path)

    def test_hub_amount_sums_removed_and_state_names_are_visible(self):
        for path in ["/state/CA/", "/industry/biotechnology/"]:
            response = self.client.get(path)
            self.assertNotContains(response, "Total raised")
            self.assertNotContains(response, "$20M")
            self.assertContains(response, "Distinct issuers (CIKs)")
            self.assertContains(response, 'href="/learn/form-d-data-methodology/"')
        self.assertContains(self.client.get("/state/CA/"), "California — Form D filings")

    def test_issuer_snapshot_uses_latest_record_and_does_not_sum_amendments(self):
        response = self.client.get(f"/issuer/{self.issuer.url_slug}/")
        self.assertEqual(response.context["latest_filing"].pk, self.amended.pk)
        self.assertNotContains(response, "Total sold")
        self.assertNotContains(response, "$5M")
        self.assertContains(response, "Latest available filing snapshot")
        self.assertContains(response, "$3,000,000")

    def test_zero_values_are_visible_and_detail_queries_do_not_load_raw_xml(self):
        self.amended.total_amount_sold = 0
        self.amended.save()
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/filing/amended/")
        self.assertFalse(any('"raw_xml"' in q["sql"] for q in queries))
        self.assertContains(response, "$0")
        doc = html.fromstring(response.content)
        self.assertEqual(doc.xpath('//dt[text()="Investors"]/following-sibling::dd/text()'), ["0"])
        self.assertContains(response, 'href="/industry/biotechnology/"')

    def test_new_guides_are_published_linked_and_idempotent(self):
        call_command("seed_articles", stdout=StringIO())
        dates = {a.slug: (a.published_at, a.updated_at) for a in Article.objects.all()}
        call_command("seed_articles", stdout=StringIO())
        self.assertEqual(dates, {a.slug: (a.published_at, a.updated_at) for a in Article.objects.all()})
        for guide in RESEARCH_GUIDES:
            path = f'/learn/{guide["slug"]}/'
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("X-Robots-Tag", response)
            self.assertContains(response, "https://www.sec.gov/")
            self.assertContains(response, "Continue your research")
            self.assertContains(self.client.get("/learn/"), f'href="{path}"')
            self.assertContains(self.client.get("/sitemap-articles.xml"), path)

    def test_guides_internal_links_resolve_without_following_external_links(self):
        call_command("seed_articles", stdout=StringIO())
        for guide in RESEARCH_GUIDES:
            doc = html.fromstring(self.client.get(f'/learn/{guide["slug"]}/').content)
            for href in set(doc.xpath('//article//a/@href')):
                if href.startswith("/"):
                    self.assertLess(self.client.get(href).status_code, 400, href)
