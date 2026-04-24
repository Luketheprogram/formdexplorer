from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from api.models import ApiKey
from filings.models import Filing, Issuer


class ApiKeyModelTests(TestCase):
    def test_generate_and_lookup(self):
        U = get_user_model()
        u = U.objects.create_user(email="a@x.com", password="pw")
        key, raw = ApiKey.generate(u, name="test")
        self.assertTrue(raw.startswith("fde_"))
        self.assertEqual(ApiKey.lookup(raw), key)
        self.assertIsNone(ApiKey.lookup("fde_wrong"))
        key.revoke()
        self.assertIsNone(ApiKey.lookup(raw))

    def test_consume_enforces_limit(self):
        U = get_user_model()
        u = U.objects.create_user(email="a@x.com", password="pw")
        key, _ = ApiKey.generate(u)
        key.monthly_limit = 2
        key.save()
        self.assertEqual(key.consume(), (True, 1))
        self.assertEqual(key.consume(), (True, 0))
        self.assertEqual(key.consume(), (False, 0))


class ApiAuthTests(TestCase):
    def _seed(self, tier="api"):
        U = get_user_model()
        u = U.objects.create_user(email="k@x.com", password="pw")
        u.subscription_tier = tier
        u.save()
        _, raw = ApiKey.generate(u)
        return u, raw

    def test_missing_key_401(self):
        self.assertEqual(self.client.get("/api/v1/filings/").status_code, 401)

    def test_wrong_tier_403(self):
        _, raw = self._seed(tier="free")
        resp = self.client.get("/api/v1/filings/", HTTP_AUTHORIZATION=f"Bearer {raw}")
        self.assertEqual(resp.status_code, 403)

    def test_valid_key_200(self):
        _, raw = self._seed(tier="api")
        resp = self.client.get("/api/v1/filings/", HTTP_AUTHORIZATION=f"Bearer {raw}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["X-RateLimit-Limit"], "10000")
        self.assertEqual(resp["X-RateLimit-Remaining"], "9999")
        self.assertEqual(resp.json()["count"], 0)

    def test_filing_detail(self):
        _, raw = self._seed(tier="api")
        i = Issuer.objects.create(cik="1234567", name="Acme LP", name_slug="acme-lp")
        Filing.objects.create(accession_number="0001234567-26-000001", issuer=i, filing_date=date(2026, 4, 20))
        resp = self.client.get(
            "/api/v1/filings/0001234567-26-000001/", HTTP_AUTHORIZATION=f"Bearer {raw}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["issuer"]["cik"], "1234567")
