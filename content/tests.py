from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from content.models import Article
from filings.models import Filing, Issuer


# Deliberately synthetic public identifiers; never used for network requests.
AD_SETTINGS = dict(
    ADSENSE_ENABLED=True,
    ADSENSE_CMP_READY=True,
    ADSENSE_CLIENT_ID="ca-pub-1234567890123456",
    ADSENSE_ARTICLE_SLOT_ID="1234567890",
    ADSENSE_GUIDES_SLOT_ID="0987654321",
    ADSENSE_CMP_SCRIPT_URL="https://fundingchoicesmessages.google.com/i/pub-1234567890123456?ers=1",
)


@override_settings(**AD_SETTINGS)
class AdvertisingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.article = Article.objects.create(
            slug="test-guide", title="Test guide", body="A useful guide.", published_at=timezone.now()
        )
        cls.issuer = Issuer.objects.create(cik="1234567", name="Acme LP", name_slug="acme-lp")
        cls.filing = Filing.objects.create(
            accession_number="0001234567-26-000001", issuer=cls.issuer, filing_date=date(2026, 4, 20)
        )

    def test_editorial_placements_follow_content_and_start_hidden(self):
        for path, slot in [("/learn/test-guide/", "1234567890"), ("/learn/", "0987654321")]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, f'data-ad-slot="{slot}"', count=1)
                self.assertContains(response, 'data-ad-container hidden')
                self.assertNotContains(response, '<script src="https://fundingchoicesmessages')
                self.assertNotContains(response, 'pagead2.googlesyndication.com')
        html = self.client.get("/learn/test-guide/").content.decode()
        self.assertLess(html.index("A useful guide."), html.index('data-ad-container'))

    def test_utility_forms_errors_and_htmx_do_not_get_ad_config(self):
        paths = ["/", "/search/", "/search/partial/", "/recent/", "/login/", "/signup/",
                 "/pricing/", "/privacy/", "/terms/", "/learn/api/", "/does-not-exist/",
                 f"/issuer/{self.issuer.url_slug}/", f"/filing/{self.filing.accession_number}/",
                 "/adv/", "/cf/", "/1a/"]
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path, HTTP_HX_REQUEST="true")
                self.assertIn(response.status_code, [200, 404])
                self.assertNotIn(b'"advertising-config"', response.content)
                self.assertNotIn(b'data-ad-slot=', response.content)

    def test_paid_and_staff_users_do_not_get_ads(self):
        for tier, staff in [("pro", False), ("api", False), ("free", True)]:
            user = get_user_model().objects.create_user(
                email=f"{tier}-{staff}@example.com", subscription_tier=tier, subscription_status="active", is_staff=staff
            )
            self.client.force_login(user)
            for path in ["/learn/", "/learn/test-guide/"]:
                self.assertNotContains(self.client.get(path), '"advertising-config"')

    def test_free_account_remains_eligible(self):
        user = get_user_model().objects.create_user(email="free@example.com")
        self.client.force_login(user)
        self.assertContains(self.client.get("/learn/test-guide/"), 'data-ad-slot=')

    def test_missing_or_invalid_configuration_fails_closed(self):
        cases = [dict(ADSENSE_ENABLED=False), dict(ADSENSE_CMP_READY=False),
                 dict(ADSENSE_CLIENT_ID=""), dict(ADSENSE_CLIENT_ID='\"><script>'),
                 dict(ADSENSE_ARTICLE_SLOT_ID=""), dict(ADSENSE_ARTICLE_SLOT_ID="invalid"),
                 dict(ADSENSE_CMP_SCRIPT_URL=""),
                 dict(ADSENSE_CMP_SCRIPT_URL="https://evil.example/tag.js"),
                 dict(ADSENSE_CMP_SCRIPT_URL="https://fundingchoicesmessages.google.com/i/pub-0000000000000000")]
        for settings in cases:
            with self.subTest(settings=settings), override_settings(**settings):
                self.assertNotContains(self.client.get("/learn/test-guide/"), '"advertising-config"')

    @override_settings(ADSENSE_ENABLED=False)
    def test_verification_works_without_ads_or_cmp(self):
        self.assertContains(self.client.get("/"), 'name="google-adsense-account" content="ca-pub-1234567890123456"')
        self.assertNotContains(self.client.get("/learn/"), 'advertising.js')
        response = self.client.get("/ads.txt")
        self.assertEqual(response["Content-Type"], "text/plain")
        self.assertEqual(response.content, b"google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0\n")
        self.assertEqual(self.client.head("/ads.txt").status_code, 200)
        self.assertEqual(self.client.post("/ads.txt").status_code, 405)

    @override_settings(ADSENSE_CLIENT_ID="")
    def test_no_fake_publisher_is_served(self):
        self.assertEqual(self.client.get("/ads.txt").status_code, 404)
        self.assertNotContains(self.client.get("/"), 'google-adsense-account')

    def test_empty_and_unpublished_articles_do_not_get_ads(self):
        self.article.body = ""
        self.article.save()
        self.assertNotContains(self.client.get("/learn/test-guide/"), '"advertising-config"')
        self.article.published_at = None
        self.article.save()
        self.assertEqual(self.client.get("/learn/test-guide/").status_code, 404)
