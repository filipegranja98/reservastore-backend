from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class StoreBrandingMigrationTests(TransactionTestCase):
    def test_existing_store_logo_and_products_survive_branding_migration(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [target for target in latest if target[0] not in ('lojas', 'marketplace')] + [('marketplace', '0006_pedido_modalidade_alter_pedido_status')] + [('lojas', '0003_alter_loja_mensalidade_loja_mensalidade_nao_negativa')]
        executor.migrate(previous)
        try:
            apps = executor.loader.project_state(previous).apps
            owner = apps.get_model('auth', 'User').objects.create(username='branding-migration', password='!')
            shop = apps.get_model('lojas', 'Loja').objects.create(dono_id=owner.pk, nome='Preserved branding', whatsapp='000', logo='logos/preserved.png')
            category = apps.get_model('lojas', 'Categoria').objects.create(loja_id=shop.pk, nome='Preserved category')
            product = apps.get_model('lojas', 'Produto').objects.create(loja_id=shop.pk, categoria_id=category.pk, nome='Preserved product', preco='10.00')
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            updated = executor.loader.project_state(latest).apps
            preserved = updated.get_model('lojas', 'Loja').objects.get(pk=shop.pk)
            self.assertEqual(preserved.nome, 'Preserved branding')
            self.assertEqual(preserved.logo.name, 'logos/preserved.png')
            self.assertEqual(preserved.cor_primaria, '#17624E')
            self.assertEqual(preserved.cor_secundaria, '#EAF1E9')
            self.assertFalse(preserved.aberta)
            self.assertEqual(updated.get_model('lojas', 'Produto').objects.get(pk=product.pk).loja_id, shop.pk)
        finally:
            MigrationExecutor(connection).migrate(latest)
