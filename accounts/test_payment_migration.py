"""Exercise the upgrade guard against legacy credits, including rollback."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PaymentMigrationTests(TransactionTestCase):
    def test_duplicate_preflight_rolls_back_and_valid_legacy_credits_survive(self):
        before = [('accounts', '0003_alter_exporttoken_id')]
        after = [('accounts', '0004_payment_integrity')]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        apps = executor.loader.project_state(before).apps
        User = apps.get_model('accounts', 'User')
        Token = apps.get_model('accounts', 'ExportToken')
        user = User.objects.create(email='migration@example.com', subscription_tier='pro', subscription_status='active')
        Token.objects.create(user=user, stripe_payment_intent='pi_duplicate')
        duplicate = Token.objects.create(user=user, stripe_payment_intent='pi_duplicate')
        Token.objects.create(user=user, stripe_payment_intent='')
        Token.objects.create(user=user, stripe_payment_intent='')
        try:
            with self.assertRaisesMessage(RuntimeError, 'manual reconciliation'):
                MigrationExecutor(connection).migrate(after)
            self.assertEqual(Token.objects.count(), 4)
            with connection.cursor() as cursor:
                columns = {c.name for c in connection.introspection.get_table_description(cursor, 'accounts_user')}
            self.assertNotIn('stripe_subscription_id', columns)
        finally:
            duplicate.delete()
            MigrationExecutor(connection).migrate(after)
        from accounts.models import User as CurrentUser, ExportToken
        self.assertTrue(CurrentUser.objects.get(pk=user.pk).is_paid)
        self.assertEqual(ExportToken.objects.count(), 3)
