import json
from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch
from xml.etree import ElementTree

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from lxml import html

from content.models import Article
from filings.models import Filing, Issuer
from filings.sitemaps import FilingSitemap, IssuerSitemap


@override_settings(SITE_URL="https://formdexplorer.com", SEO_INDEXING_ENABLED=True, DEBUG=True)
class SEOTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.issuer = Issuer.objects.create(cik="1234567", name='Acme "Research" & </script> LP', state="CA")
        cls.empty = Issuer.objects.create(cik="7654321", name="Empty company", state="NY")
        Filing.objects.bulk_create([
            Filing(issuer=cls.issuer, accession_number=f"0001234567-26-{i:06}",
                   filing_date=date(2026, 10, 1), industry_group="Biotechnology")
            for i in range(1, 52)
        ])
        cls.article = Article.objects.create(slug="guide", title='A "quoted" & </script> guide',
            body="Useful filing research.", published_at=timezone.now() - timedelta(days=1))
        Article.objects.create(slug="future", title="Future", body="Upcoming.", published_at=timezone.now() + timedelta(days=5))
        Article.objects.create(slug="draft", title="Draft", body="Not ready.")
        Article.objects.create(slug="empty", title="Empty", body="   ", published_at=timezone.now())

    def setUp(self):
        cache.clear()
        self.client = Client(HTTP_HOST="formdexplorer.com")

    def document(self, response):
        return html.fromstring(response.content)

    def locations(self, response):
        self.assertEqual(response.status_code, 200)
        return [node.text for node in ElementTree.fromstring(response.content).iter()
                if node.tag.endswith("}loc")]

    def test_home_has_single_canonical_and_real_internal_links(self):
        response = self.client.get("/?utm_source=test")
        doc = self.document(response)
        self.assertEqual(doc.xpath('//link[@rel="canonical"]/@href'), ["https://formdexplorer.com/"])
        self.assertEqual(doc.xpath('//meta[@property="og:url"]/@content'), ["https://formdexplorer.com/"])
        self.assertContains(response, 'href="/state/CA/"')
        self.assertNotContains(response, 'href="/state/NY/"')
        self.assertNotContains(response, 'href="/industry/coal-mining/"')
        self.assertNotIn("X-Robots-Tag", response)

    def test_sitemap_index_links_every_batch_with_canonical_origin(self):
        with patch.object(FilingSitemap, "limit", 20), patch.object(IssuerSitemap, "limit", 1):
            sections = self.locations(self.client.get("/sitemap.xml", HTTP_HOST="alternate.example"))
            self.assertIn("https://formdexplorer.com/sitemap-filings.xml?p=3", sections)
            urls = []
            for section in sections:
                self.assertTrue(section.startswith("https://formdexplorer.com/"))
                urls.extend(self.locations(self.client.get(section.replace("https://formdexplorer.com", ""))))
            filing_urls = [u for u in urls if "/filing/" in u]
            self.assertEqual(len(filing_urls), 51)
            self.assertEqual(len(set(filing_urls)), 51)
            self.assertIn(f"https://formdexplorer.com/issuer/{self.issuer.url_slug}/", urls)
            self.assertNotIn(f"https://formdexplorer.com/issuer/{self.empty.url_slug}/", urls)
            self.assertNotIn("https://formdexplorer.com/state/NY/", urls)
            self.assertFalse(any("?page=" in u or "/search/" in u for u in urls))
            self.assertIn("https://formdexplorer.com/learn/guide/", urls)
            for slug in ["future", "draft", "empty"]:
                self.assertNotIn(f"https://formdexplorer.com/learn/{slug}/", urls)

    def test_sitemap_does_not_fetch_raw_xml_and_uses_configured_origin(self):
        self.assertIn("raw_xml", FilingSitemap().items().first().get_deferred_fields())
        urls = self.locations(self.client.get("/sitemap-filings.xml", HTTP_HOST="alternate.example"))
        self.assertTrue(all(u.startswith("https://formdexplorer.com/") for u in urls))

    def test_unknown_sitemap_sections_and_pages_are_404(self):
        for path in ["/sitemap-missing.xml", "/sitemap-filings.xml?p=bogus", "/sitemap-filings.xml?p=999"]:
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_pagination_is_bounded_crawlable_self_canonical_and_noindex(self):
        for path in [f"/issuer/{self.issuer.url_slug}/", "/industry/biotechnology/", "/state/CA/"]:
            with self.subTest(path=path):
                first = self.client.get(path)
                self.assertContains(first, 'href="?page=2"')
                self.assertNotIn("X-Robots-Tag", first)
                response = self.client.get(path + "?page=2&utm_source=test")
                doc = self.document(response)
                self.assertEqual(doc.xpath('//link[@rel="canonical"]/@href'), ["https://formdexplorer.com" + path + "?page=2"])
                self.assertIn("Page 2", doc.xpath('//title/text()')[0])
                self.assertEqual(response["X-Robots-Tag"], "noindex, follow")
                self.assertEqual(doc.xpath('//meta[@name="robots"]/@content'), ["noindex, follow"])
                self.assertContains(response, f'href="{path}"')
                if "/issuer/" in path:
                    self.assertEqual(len(response.context["filings"]), 1)
                    self.assertEqual(len(first.context["filings"]), 50)
                for page in ["0", "-1", "bogus", "999"]:
                    self.assertEqual(self.client.get(path + "?page=" + page).status_code, 404)

    def test_alias_redirects_preserve_pagination(self):
        self.assertRedirects(self.client.get("/issuer/old-name-1234567/?page=2"),
            f"/issuer/{self.issuer.url_slug}/?page=2", status_code=301, fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/state/ca/?page=2"), "/state/CA/?page=2", status_code=301, fetch_redirect_response=False)

    def test_utility_and_search_pages_have_noindex_headers(self):
        for path in ["/search/", "/search/partial/", "/adv/", "/cf/", "/1a/", "/login/",
                     "/adv/search/partial/", "/cf/search/partial/", "/1a/search/partial/",
                     "/signup/", "/account/", "/saved-searches/", "/watchlist/", "/export/csv/",
                     "/checkout/success/", "/api/filings/", "/missing/"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertIn("noindex", response["X-Robots-Tag"])
                if response.status_code == 200 and b"<html" in response.content:
                    self.assertIn("noindex", self.document(response).xpath('//meta[@name="robots"]/@content')[0])
        self.assertIn("noindex", self.client.get("/", HTTP_HX_REQUEST="true")["X-Robots-Tag"])

    def test_authenticated_private_pages_remain_noindex(self):
        user = get_user_model().objects.create_user(email="seo-private@example.com")
        self.client.force_login(user)
        for path in ["/account/", "/account/api-keys/", "/saved-searches/", "/watchlist/"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn("noindex", response["X-Robots-Tag"])
            self.assertIn("noindex", self.document(response).xpath('//meta[@name="robots"]/@content')[0])

    def test_empty_hubs_and_issuer_are_not_indexable(self):
        for path in [f"/issuer/{self.empty.url_slug}/", "/industry/coal-mining/", "/learn/empty/"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn("noindex", response["X-Robots-Tag"])

    def test_unpublished_articles_are_unavailable(self):
        for slug in ["future", "draft"]:
            self.assertEqual(self.client.get(f"/learn/{slug}/").status_code, 404)
        response = self.client.get("/learn/")
        for slug in ["future", "draft", "empty"]:
            self.assertNotContains(response, f'href="/learn/{slug}/"')

    def test_structured_data_is_valid_json_and_preserves_text(self):
        for path, kind, field, expected in [
            ("/learn/guide/", "Article", "headline", self.article.title),
            (f"/issuer/{self.issuer.url_slug}/", "Organization", "name", self.issuer.name),
        ]:
            doc = self.document(self.client.get(path))
            scripts = doc.xpath('//script[@type="application/ld+json"]/text()')
            self.assertEqual(len(scripts), 1)
            graph = json.loads(scripts[0])["@graph"]
            self.assertTrue(any(x["@type"] == kind and x.get(field) == expected for x in graph))
            self.assertTrue(any(x["@type"] == "BreadcrumbList" for x in graph))
            self.assertNotIn("</script>", scripts[0])

    def test_robots_allows_crawling_noindex_and_static_resources(self):
        response = self.client.get("/robots.txt")
        self.assertContains(response, "Sitemap: https://formdexplorer.com/sitemap.xml")
        self.assertNotContains(response, "Disallow: /search/")
        self.assertNotContains(response, "Disallow: /static/")

    @override_settings(GOOGLE_SITE_VERIFICATION="real-token-from-google")
    def test_optional_search_console_verification(self):
        self.assertContains(self.client.get("/"), 'name="google-site-verification" content="real-token-from-google"')

    @override_settings(SEO_INDEXING_ENABLED=False)
    def test_staging_switch_noindexes_pages(self):
        response = self.client.get("/")
        self.assertIn("noindex", response["X-Robots-Tag"])
        self.assertContains(response, 'name="robots" content="noindex, follow"')

    @override_settings(DEBUG=False, CANONICAL_REDIRECT_HOSTS={"www.formdexplorer.com"},
                       STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
    def test_production_alias_redirect_and_unknown_host_noindex(self):
        response = self.client.get("/industry/biotechnology/?page=2", HTTP_HOST="www.formdexplorer.com", secure=True)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://formdexplorer.com/industry/biotechnology/?page=2")
        self.assertIn("noindex", self.client.get("/", HTTP_HOST="preview.example", secure=True)["X-Robots-Tag"])
        self.assertNotIn("X-Robots-Tag", self.client.get("/", secure=True))
        # Never redirect payments or API requests across hosts.
        self.assertNotEqual(self.client.post("/stripe/webhook/", HTTP_HOST="www.formdexplorer.com", secure=True).status_code, 301)

    def test_seeding_keeps_real_publication_and_modification_dates(self):
        article_data = [{"slug": "guide", "title": self.article.title,
                         "meta_description": self.article.meta_description, "body": self.article.body}]
        original = (self.article.published_at, self.article.updated_at)
        with patch("content.management.commands.seed_articles.ARTICLES", article_data):
            call_command("seed_articles", stdout=StringIO())
            self.article.refresh_from_db()
            self.assertEqual((self.article.published_at, self.article.updated_at), original)
            article_data[0]["body"] = "Updated research."
            call_command("seed_articles", stdout=StringIO())
            self.article.refresh_from_db()
            self.assertEqual(self.article.published_at, original[0])
            self.assertGreater(self.article.updated_at, original[1])
