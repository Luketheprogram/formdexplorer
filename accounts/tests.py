from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import ExportToken


class UserModelTests(TestCase):
    def test_email_is_username(self):
        U = get_user_model()
        u = U.objects.create_user(email="a@b.com", password="pw")
        self.assertEqual(u.email, "a@b.com")
        self.assertFalse(u.is_staff)
        self.assertEqual(u.subscription_tier, "free")
        self.assertFalse(u.is_paid)

    def test_superuser(self):
        U = get_user_model()
        su = U.objects.create_superuser(email="admin@x.com", password="pw")
        self.assertTrue(su.is_staff)
        self.assertTrue(su.is_superuser)

    def test_export_token_consume(self):
        U = get_user_model()
        u = U.objects.create_user(email="x@y.com", password="pw")
        t = ExportToken.objects.create(user=u)
        self.assertTrue(t.is_unused)
        t.consume()
        t.refresh_from_db()
        self.assertIsNotNone(t.used_at)
        self.assertFalse(t.is_unused)


class AuthFlowTests(TestCase):
    def test_signup_logs_in(self):
        resp = self.client.post(
            "/signup/", {"email": "new@x.com", "password": "supersecret123!"}, follow=False
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_signup_rejects_duplicate(self):
        U = get_user_model()
        U.objects.create_user(email="dup@x.com", password="pw")
        resp = self.client.post("/signup/", {"email": "dup@x.com", "password": "supersecret123!"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "already exists")

    def test_account_requires_login(self):
        resp = self.client.get("/account/")
        self.assertEqual(resp.status_code, 302)


class ExportGatingTests(TestCase):
    def test_free_user_redirected(self):
        U = get_user_model()
        u = U.objects.create_user(email="f@x.com", password="pw")
        self.client.force_login(u)
        resp = self.client.get("/export/csv/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/pricing/", resp["Location"])

    def test_paid_user_gets_csv(self):
        U = get_user_model()
        u = U.objects.create_user(email="p@x.com", password="pw")
        u.subscription_tier = U.SUBSCRIPTION_PRO
        u.save()
        self.client.force_login(u)
        resp = self.client.get("/export/csv/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")

    def test_token_user_consumes_token(self):
        U = get_user_model()
        u = U.objects.create_user(email="t@x.com", password="pw")
        ExportToken.objects.create(user=u)
        self.client.force_login(u)
        resp = self.client.get("/export/csv/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(u.export_tokens.filter(used_at__isnull=True).count(), 0)
