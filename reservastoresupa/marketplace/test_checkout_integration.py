from decimal import Decimal
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from rest_framework.test import APITestCase
from .models import Carrinho, ItemCarrinho, Pedido, ItemPedido, EventoPedido, AreaEntrega
from . import tests as fixtures
from reservastoresupa.lojas.models import Produto


class CheckoutIntegrationTests(APITestCase):
    setUp = fixtures.MarketplaceTests.setUp
    add = fixtures.MarketplaceTests.add
    payload = fixtures.MarketplaceTests.payload
    order = fixtures.MarketplaceTests.order

    def preview(self, **changes):
        return self.client.post("/api/pedidos/previa/", self.payload(**changes), format="json")

    def test_preview_computes_total_without_changing_any_cart_or_creating_order(self):
        self.add()
        self.add(self.l2, self.p2, 3)
        original = list(Carrinho.objects.values("id", "cliente_id", "loja_id", "atualizado_em"))
        original_items = list(ItemCarrinho.objects.values())
        self.area1.prazo_estimado_minutos = 30
        self.area1.save()
        for _ in range(2):
            response = self.preview()
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["subtotal"], "20.00")
            self.assertEqual(response.data["taxa_entrega"], "3.50")
            self.assertEqual(response.data["total"], "23.50")
            self.assertEqual(response.data["prazo_estimado_minutos"], 30)
            self.assertEqual(response.data["endereco"]["id"], self.addr1.pk)
            self.assertEqual(response.data["itens"][0]["produto"], self.p1.pk)
            self.assertEqual(response.data["itens"][0]["total"], "20.00")
        self.assertEqual(list(Carrinho.objects.values("id", "cliente_id", "loja_id", "atualizado_em")), original)
        self.assertEqual(list(ItemCarrinho.objects.values()), original_items)
        self.assertFalse(Pedido.objects.exists())
        self.assertFalse(ItemPedido.objects.exists())
        self.assertFalse(EventoPedido.objects.exists())

    def test_preview_and_checkout_agree_and_order_keeps_original_delivery_estimate(self):
        self.add()
        self.area1.prazo_estimado_minutos = 40
        self.area1.save()
        preview = self.preview().data
        response = self.client.post("/api/pedidos/", self.payload())
        self.assertEqual(response.status_code, 201)
        for field in ["subtotal", "taxa_entrega", "total", "prazo_estimado_minutos", "meio_pagamento"]:
            self.assertEqual(response.data[field], preview[field])
        pk = response.data["id"]
        self.area1.prazo_estimado_minutos = 80
        self.area1.save()
        response = self.client.get(f"/api/pedidos/{pk}/")
        self.assertEqual(response.data["prazo_estimado_minutos"], 40)

    def test_checkout_revalidates_price_fee_and_estimate_after_preview(self):
        self.add()
        self.assertEqual(self.preview().data["total"], "23.50")
        self.p1.preco = Decimal("12.00")
        self.p1.save()
        self.area1.taxa = Decimal("5.00")
        self.area1.prazo_estimado_minutos = 45
        self.area1.save()
        response = self.client.post("/api/pedidos/", self.payload())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["total"], "29.00")
        self.assertEqual(response.data["prazo_estimado_minutos"], 45)

    def test_no_delivery_estimate_is_invented_for_existing_areas(self):
        self.add()
        self.assertIsNone(self.preview().data["prazo_estimado_minutos"])
        response = self.client.post("/api/pedidos/", self.payload())
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data["prazo_estimado_minutos"])

    def test_preview_rejects_other_customer_address_and_other_store_area(self):
        self.add()
        self.assertEqual(self.preview(endereco=self.addr2.pk).status_code, 404)
        self.assertEqual(self.preview(area_entrega=self.area2.pk).status_code, 404)
        self.assertEqual(self.preview(loja=self.l2.pk).status_code, 404)
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertEqual(ItemCarrinho.objects.count(), 1)

    def test_preview_does_not_expose_another_customers_cart(self):
        self.add()
        self.client.force_authenticate(self.c2)
        response = self.preview(endereco=self.addr2.pk)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Carrinho.objects.count(), 1)
        self.assertFalse(Pedido.objects.exists())

    def test_preview_rejects_forged_values_and_idempotency_key(self):
        self.add()
        for changes in [{"total": "0.01"}, {"taxa_entrega": "0.00"}, {"cliente": self.c2.pk},
                        {"prazo_estimado_minutos": 1}, {"chave_checkout": "f4318180-c35b-4acc-9b2d-ff31c2bda497"}]:
            self.assertEqual(self.preview(**changes).status_code, 400)
        self.assertFalse(Pedido.objects.exists())

    def test_preview_obeys_unavailable_store_product_area_and_payment_rules(self):
        self.add()
        self.assertEqual(self.preview(meio_pagamento="cartao_na_entrega").status_code, 400)
        self.area1.ativa = False
        self.area1.save()
        self.assertEqual(self.preview().status_code, 404)
        self.area1.ativa = True
        self.area1.save()
        self.p1.ativo = False
        self.p1.save()
        self.assertEqual(self.preview().status_code, 400)
        self.p1.ativo = True
        self.p1.save()
        self.l1.ativa = False
        self.l1.save()
        self.assertEqual(self.preview().status_code, 400)
        self.assertEqual(ItemCarrinho.objects.count(), 1)
        self.assertFalse(Pedido.objects.exists())

    def test_preview_requires_customer_role_and_authentication(self):
        self.add()
        for user in [self.m1, self.admin]:
            self.client.force_authenticate(user)
            self.assertEqual(self.preview().status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.preview().status_code, 401)

    def test_preview_missing_or_empty_cart_creates_nothing(self):
        self.assertEqual(self.preview().status_code, 404)
        self.add()
        ItemCarrinho.objects.all().delete()
        self.assertEqual(self.preview().status_code, 400)
        self.assertFalse(Pedido.objects.exists())

    def test_delivery_estimate_owned_configuration_and_validation(self):
        self.client.force_authenticate(self.m1)
        url = f"/api/lojista/areas-entrega/{self.area1.pk}/"
        for value in [0, -1, 32768, 2.5]:
            self.assertEqual(self.client.patch(url, {"prazo_estimado_minutos": value}).status_code, 400)
        response = self.client.patch(url, {"prazo_estimado_minutos": 25})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["prazo_estimado_minutos"], 25)
        self.assertEqual(self.client.patch(f"/api/lojista/areas-entrega/{self.area2.pk}/", {"prazo_estimado_minutos": 25}).status_code, 404)
        self.client.force_authenticate(None)
        public = self.client.get(f"/api/catalogo/lojas/{self.l1.pk}/areas-entrega/")
        self.assertEqual(public.data[0]["prazo_estimado_minutos"], 25)
        self.client.force_authenticate(self.m1)
        self.assertEqual(self.client.patch(url, {"prazo_estimado_minutos": None}, format="json").status_code, 200)

    def test_invalid_estimate_is_also_blocked_by_database(self):
        for value in [0, 32768]:
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    AreaEntrega.objects.filter(pk=self.area1.pk).update(prazo_estimado_minutos=value)


class PaginationIntegrationTests(APITestCase):
    setUp = fixtures.MarketplaceTests.setUp
    add = fixtures.MarketplaceTests.add
    payload = fixtures.MarketplaceTests.payload
    order = fixtures.MarketplaceTests.order

    def test_catalog_legacy_arrays_and_paginated_results_are_both_supported(self):
        self.client.force_authenticate(None)
        legacy = self.client.get("/api/catalogo/lojas/")
        self.assertIsInstance(legacy.data, list)
        first = self.client.get("/api/catalogo/lojas/?page=1&page_size=1")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["count"], 2)
        self.assertEqual(len(first.data["results"]), 1)
        self.assertIsNone(first.data["previous"])
        second = self.client.get(first.data["next"])
        self.assertIsNone(second.data["next"])
        self.assertNotEqual(first.data["results"][0]["id"], second.data["results"][0]["id"])
        self.assertEqual(self.client.get(second.data["previous"]).data["results"], first.data["results"])

    def test_previous_link_keeps_pagination_enabled_when_using_default_page_size(self):
        Produto.objects.bulk_create([Produto(loja=self.l1, categoria=self.cat1, nome=f"Produto {n:02d}", preco=1) for n in range(24)])
        self.client.force_authenticate(None)
        path = f"/api/catalogo/lojas/{self.l1.pk}/produtos/"
        first = self.client.get(path + "?page=1")
        self.assertEqual(len(first.data["results"]), 20)
        self.assertEqual(first.data["count"], 25)
        second = self.client.get(first.data["next"])
        self.assertEqual(len(second.data["results"]), 5)
        self.assertIn("page=1", second.data["previous"])
        self.assertEqual(len(self.client.get(second.data["previous"]).data["results"]), 20)
        self.assertFalse({p["id"] for p in first.data["results"]} & {p["id"] for p in second.data["results"]})

    def test_paginated_public_actions_exclude_foreign_or_inactive_data(self):
        self.p1.ativo = False
        self.p1.save()
        self.client.force_authenticate(None)
        products = self.client.get(f"/api/catalogo/lojas/{self.l1.pk}/produtos/?page_size=1")
        self.assertEqual(products.data["count"], 0)
        self.assertEqual(products.data["results"], [])
        categories = self.client.get(f"/api/catalogo/lojas/{self.l1.pk}/categorias/?page_size=1")
        self.assertEqual(categories.data["count"], 1)
        self.assertEqual(categories.data["results"][0]["id"], self.cat1.pk)
        areas = self.client.get(f"/api/catalogo/lojas/{self.l1.pk}/areas-entrega/?page_size=1")
        self.assertEqual(areas.data["results"][0]["id"], self.area1.pk)
        self.l1.ativa = False
        self.l1.save()
        self.assertEqual(self.client.get(f"/api/catalogo/lojas/{self.l1.pk}/produtos/?page=1").status_code, 404)

    def test_paginated_private_lists_preserve_owner_scope(self):
        response = self.client.get("/api/enderecos/?page_size=1")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.addr1.pk)
        self.client.force_authenticate(self.m1)
        for path, pk in [("produtos", self.p1.pk), ("categorias", self.cat1.pk), ("lojas", self.l1.pk), ("lojista/areas-entrega", self.area1.pk)]:
            response = self.client.get(f"/api/{path}/?page=1&page_size=1")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["count"], 1)
            self.assertEqual(response.data["results"][0]["id"], pk)

    def test_pagination_counts_do_not_leak_other_customers_or_merchants_orders(self):
        own_ids = {self.order(), self.order()}
        self.client.force_authenticate(self.c2)
        self.add()
        response = self.client.post("/api/pedidos/", self.payload(endereco=self.addr2.pk))
        self.assertEqual(response.status_code, 201)
        self.client.force_authenticate(self.c1)
        response = self.client.get("/api/pedidos/?page=1&page_size=1")
        self.assertEqual(response.data["count"], 2)
        self.assertIn(response.data["results"][0]["id"], own_ids)
        self.client.force_authenticate(self.m2)
        response = self.client.get("/api/lojista/pedidos/?page=1")
        self.assertEqual(response.data["count"], 0)
        self.client.force_authenticate(self.m1)
        self.assertEqual(self.client.get("/api/lojista/pedidos/?page=1").data["count"], 3)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/administracao/pedidos/?page=1").data["count"], 3)

    def test_invalid_sizes_and_pages_are_rejected(self):
        self.client.force_authenticate(None)
        for size in ["0", "-1", "101", "abc", "1.5", ""]:
            response = self.client.get("/api/catalogo/lojas/", {"page_size": size})
            self.assertEqual(response.status_code, 400)
        for page in ["0", "-1", "abc", "999"]:
            self.assertEqual(self.client.get("/api/catalogo/lojas/", {"page": page}).status_code, 404)

    def test_unauthorized_lists_do_not_return_paginated_counts(self):
        for path in ["administracao/usuarios", "administracao/lojas", "lojista/pedidos"]:
            self.assertEqual(self.client.get(f"/api/{path}/?page=1").status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/pedidos/?page=1").status_code, 401)


class DeliveryEstimateMigrationTests(TransactionTestCase):
    """A new optional estimate must not rewrite orders or invent delivery times."""
    def test_existing_orders_areas_and_carts_survive_nullable_estimate_migration(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        previous = [("marketplace", "0004_pedido_chave_checkout_alter_areaentrega_taxa_and_more"), ("lojas", "0003_alter_loja_mensalidade_loja_mensalidade_nao_negativa")]
        current = [("marketplace", "0005_areaentrega_prazo_estimado_minutos_and_more"), ("lojas", "0003_alter_loja_mensalidade_loja_mensalidade_nao_negativa")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(previous)
        try:
            apps = executor.loader.project_state(previous).apps
            User = apps.get_model("auth", "User")
            Loja = apps.get_model("lojas", "Loja")
            Categoria = apps.get_model("lojas", "Categoria")
            Produto = apps.get_model("lojas", "Produto")
            Area = apps.get_model("marketplace", "AreaEntrega")
            Order = apps.get_model("marketplace", "Pedido")
            Cart = apps.get_model("marketplace", "Carrinho")
            CartItem = apps.get_model("marketplace", "ItemCarrinho")
            buyer = User.objects.create(username="migration-buyer", password="!")
            merchant = User.objects.create(username="migration-merchant", password="!")
            shop = Loja.objects.create(dono_id=merchant.pk, nome="Preserved", whatsapp="000")
            category = Categoria.objects.create(loja_id=shop.pk, nome="Preserved")
            product = Produto.objects.create(loja_id=shop.pk, categoria_id=category.pk, nome="Preserved", preco="10")
            area = Area.objects.create(loja_id=shop.pk, condominio="Reserva", condominio_normalizado="reserva", taxa="3.50")
            address = {"condominio": "Reserva", "bloco": "A", "apartamento": "101"}
            order = Order.objects.create(cliente_id=buyer.pk, loja_id=shop.pk, endereco=address, meio_pagamento="pix", subtotal="20.00", taxa_entrega="3.50", total="23.50")
            cart = Cart.objects.create(cliente_id=buyer.pk, loja_id=shop.pk)
            CartItem.objects.create(carrinho_id=cart.pk, produto_id=product.pk, quantidade=2)
            executor = MigrationExecutor(connection)
            executor.migrate(current)
            updated = executor.loader.project_state(current).apps
            preserved = updated.get_model("marketplace", "Pedido").objects.get(pk=order.pk)
            self.assertEqual(preserved.total, Decimal("23.50"))
            self.assertEqual(preserved.endereco, address)
            self.assertIsNone(preserved.prazo_estimado_minutos)
            self.assertIsNone(updated.get_model("marketplace", "AreaEntrega").objects.get(pk=area.pk).prazo_estimado_minutos)
            self.assertEqual(updated.get_model("marketplace", "ItemCarrinho").objects.get(carrinho_id=cart.pk).quantidade, 2)
        finally:
            MigrationExecutor(connection).migrate(latest)
