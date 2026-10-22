"""Render real pages: metadata must be unique, escaped, and consistent across tags."""
from datetime import date
from html.parser import HTMLParser
import json
import re

from django.test import TestCase
from django.utils import timezone

from advisers.models import Adviser
from content.management.commands.seed_articles import ARTICLES
from content.models import Article
from crowdfunding.models import CrowdfundingFiling
from filings.models import Filing, Issuer, RelatedPerson
from rega.models import Form1AFiling


class HeadParser(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.titles = []
        self.meta = {}
        self.in_title = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.titles.append("")
            self.in_title = True
        if tag == "meta":
            key = attrs.get("name") or attrs.get("property")
            self.meta.setdefault(key, []).append(attrs.get("content", ""))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.titles[-1] += data


class PageMetadataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.issuer = Issuer.objects.create(cik="1234567", name='Acme & "Partners"', state="CA")
        cls.filing = Filing.objects.create(
            issuer=cls.issuer, accession_number="0001234567-26-000001",
            filing_date=date(2026, 4, 20), industry_group="Real Estate",
            total_offering_amount=10000000, total_amount_sold=0,
        )
        cls.adviser = Adviser.objects.create(crd="123456", name=cls.issuer.name)
        cls.cf = CrowdfundingFiling.objects.create(
            issuer=cls.issuer, accession_number="0001234567-26-000002", filing_date=date(2026, 4, 20),
        )
        cls.rega = Form1AFiling.objects.create(
            issuer=cls.issuer, accession_number="0001234567-26-000003", filing_date=date(2026, 4, 20),
        )
        cls.person = RelatedPerson.objects.create(filing=cls.filing, name="Jane Example", relationship="Director")
        for data in ARTICLES:
            Article.objects.create(**data, published_at=timezone.now())

    def head(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        head = HeadParser(response.content.decode())
        self.assertEqual(len(head.titles), 1, path)
        title = head.titles[0]
        self.assertEqual(title.count("Form D Explorer"), 1, path)
        self.assertTrue(title.strip(), path)
        for key in ("description", "og:title", "og:description", "twitter:title", "twitter:description"):
            self.assertEqual(len(head.meta[key]), 1, (path, key))
            self.assertTrue(head.meta[key][0].strip(), (path, key))
        description = head.meta["description"][0]
        self.assertEqual(head.meta["og:title"], [title])
        self.assertEqual(head.meta["twitter:title"], [title])
        self.assertEqual(head.meta["og:description"], [description])
        self.assertEqual(head.meta["twitter:description"], [description])
        for value in (title, description):
            self.assertEqual(value, " ".join(value.split()))
            self.assertNotIn("None", value)
            self.assertNotIn("{{", value)
        return title, description

    def test_public_pages_have_distinct_metadata_and_matching_social_tags(self):
        paths = ["/", "/search/", "/recent/", "/industry/real-estate/", "/state/CA/",
                 "/adv/", "/cf/", "/1a/", "/learn/", "/learn/api/", "/pricing/", "/privacy/", "/terms/",
                 f"/issuer/{self.issuer.url_slug}/", f"/filing/{self.filing.accession_number}/",
                 f"/adv/{self.adviser.crd}/", f"/cf/{self.cf.accession_number}/",
                 f"/1a/{self.rega.accession_number}/", f"/person/{self.person.name_slug}/"]
        paths += [f"/learn/{data['slug']}/" for data in ARTICLES]
        titles, descriptions = set(), set()
        for path in paths:
            with self.subTest(path=path):
                title, description = self.head(path)
                self.assertNotIn(title, titles)
                self.assertNotIn(description, descriptions)
                titles.add(title)
                descriptions.add(description)

    def test_keywords_and_state_names_describe_the_actual_page(self):
        self.assertIn("Private Placement Database", self.head("/")[0])
        self.assertIn("Search SEC Form D Filings", self.head("/search/")[0])
        self.assertIn("in our database", self.head("/recent/")[1])
        self.assertIn("California", self.head("/state/CA/")[0])
        self.assertIn("Real Estate", self.head("/industry/real-estate/")[0])
        self.assertIn("Investment Adviser", self.head("/adv/")[0])
        self.assertIn("Crowdfunding", self.head("/cf/")[0])
        self.assertIn("Reg A+", self.head("/1a/")[0])

    def test_same_name_issuers_and_advisers_remain_distinct(self):
        other = Issuer.objects.create(cik="7654321", name=self.issuer.name)
        self.assertNotEqual(self.head(f"/issuer/{self.issuer.url_slug}/"), self.head(f"/issuer/{other.url_slug}/"))
        other_adviser = Adviser.objects.create(crd="654321", name=self.adviser.name)
        self.assertNotEqual(self.head("/adv/123456/"), self.head(f"/adv/{other_adviser.crd}/"))

    def test_same_day_filings_are_unique_for_every_filing_family(self):
        for model, record, prefix in [(Filing, self.filing, "filing"),
                                      (CrowdfundingFiling, self.cf, "cf"),
                                      (Form1AFiling, self.rega, "1a")]:
            with self.subTest(model=model):
                other = model.objects.create(issuer=self.issuer, filing_date=record.filing_date,
                                             accession_number="0001234567-26-000099")
                first = self.head(f"/{prefix}/{record.accession_number}/")
                second = self.head(f"/{prefix}/{other.accession_number}/")
                self.assertNotEqual(first[0], second[0])
                self.assertNotEqual(first[1], second[1])
                for text in second:
                    self.assertIn(other.accession_number, text)
                    self.assertIn("2026-04-20", text)

    def test_amendments_reports_and_withdrawals_do_not_imply_new_raises(self):
        for record, prefix, forms in [
            (self.filing, "filing", ["D", "D/A"]),
            (self.cf, "cf", [value for value, _ in CrowdfundingFiling.FORM_TYPES]),
            (self.rega, "1a", [value for value, _ in Form1AFiling.FORM_TYPES]),
        ]:
            for form in forms:
                with self.subTest(form=form):
                    record.form_type = form
                    record.save()
                    title, description = self.head(f"/{prefix}/{record.accession_number}/")
                    self.assertIn(f"Form {form}", title)
                    self.assertIn(f"Form {form}", description)
                    for claim in ("raised $", "secured", "approved", "audited", "$10,000,000"):
                        self.assertNotIn(claim, description)

    def test_long_names_whitespace_and_html_are_safe_without_losing_identifiers(self):
        self.issuer.name = '  Acme\n "Quoted" & <script>  ' + "Very Long Name " * 15
        self.issuer.save()
        path = f"/filing/{self.filing.accession_number}/"
        title, description = self.head(path)
        self.assertIn('Acme "Quoted" & <script>', title)
        self.assertIn(self.filing.accession_number, title)
        self.assertIn(self.filing.accession_number, description)
        self.assertLess(len(title), 170)
        raw_head = self.client.get(path).content.decode().split("</head>")[0]
        self.assertIn("&lt;script&gt;", raw_head)
        self.assertIn("&quot;Quoted&quot;", raw_head)
        self.assertNotIn("<script> Very Long Name", raw_head)

    def test_pagination_uses_resolved_page_without_duplicate_branding(self):
        Filing.objects.bulk_create([
            Filing(issuer=self.issuer, accession_number=f"0001234567-26-{i:06d}",
                   filing_date=date(2026, 4, 20), industry_group="Real Estate")
            for i in range(100, 151)
        ])
        for path in [f"/issuer/{self.issuer.url_slug}/", "/industry/real-estate/", "/state/CA/"]:
            first = self.head(path)
            second = self.head(path + "?page=2")
            self.assertNotEqual(first, second)
            self.assertIn("Page 2", second[0])
            self.assertTrue(second[1].startswith("Page 2."))
            self.assertEqual(first, self.head(path + "?page=invalid"))

    def test_search_queries_do_not_pollute_canonical_metadata_or_branding(self):
        for path in ["/search/", "/adv/", "/cf/", "/1a/"]:
            with self.subTest(path=path):
                self.assertEqual(self.head(path), self.head(path + '?q=%22%3E%3Cscript%3E&utm_source=test'))

    def test_other_search_collections_have_distinct_paginated_metadata(self):
        Adviser.objects.bulk_create([Adviser(crd=str(i), name=f"Adviser {i}") for i in range(100, 151)])
        for model in [CrowdfundingFiling, Form1AFiling]:
            model.objects.bulk_create([
                model(issuer=self.issuer, accession_number=f"0001234567-26-{i:06d}",
                      filing_date=date(2026, 4, 20)) for i in range(100, 151)
            ])
        for path in ["/adv/", "/cf/", "/1a/"]:
            first = self.head(path)
            second = self.head(path + "?page=2")
            self.assertNotEqual(first[0], second[0])
            self.assertNotEqual(first[1], second[1])
            self.assertIn("Page 2", second[0])

    def test_guide_fallback_uses_body_and_preserves_authored_metadata(self):
        article = Article.objects.create(slug="custom-guide", title="Custom Guide | Form D Explorer",
                                         body="Learn **offering amounts** &amp; [filing dates](/recent/).",
                                         meta_description="  ", published_at=timezone.now())
        title, description = self.head("/learn/custom-guide/")
        self.assertEqual(title, "Custom Guide | Form D Explorer")
        self.assertEqual(description, "Learn offering amounts & filing dates.")
        article.meta_description = '  A custom\n description with "quotes" & context.  '
        article.save()
        self.assertEqual(self.head("/learn/custom-guide/")[1], 'A custom description with "quotes" & context.')
        article.body = article.meta_description = ""
        article.save()
        self.assertIn("educational guide", self.head("/learn/custom-guide/")[1])

    def test_guide_metadata_does_not_change_visible_headings_or_require_reseeding(self):
        for data in ARTICLES:
            response = self.client.get(f"/learn/{data['slug']}/")
            self.assertContains(response, data["title"], html=False)
        description = self.head("/learn/form-d-vs-form-1a/")[1]
        self.assertNotIn("register private offerings", description)
        self.assertIn("notices", description)
        html = self.client.get("/learn/form-d-vs-form-1a/").content.decode()
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        article = next(json.loads(block) for block in blocks if json.loads(block).get("@type") == "Article")
        self.assertEqual(article["description"], description)

    def test_partials_do_not_emit_document_metadata(self):
        for path in ["/search/partial/", "/adv/search/partial/", "/cf/search/partial/", "/1a/search/partial/"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "<title>")
            self.assertNotContains(response, 'name="description"')

    def test_existing_crawl_directives_and_canonical_are_preserved(self):
        self.assertContains(self.client.get("/search/"), 'name="robots" content="noindex,follow"')
        self.assertContains(self.client.get("/recent/"), 'rel="canonical" href="http://localhost:8000/recent/"')
