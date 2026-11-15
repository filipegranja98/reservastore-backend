import uuid
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from reservastoresupa.lojas.models import Loja, Categoria, Produto
from .models import Perfil, Endereco, AreaEntrega, Carrinho, ItemCarrinho, Pedido, EventoPedido


class MarketplaceTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.m1 = User.objects.create_user("merchant1", password="merchant-pass")
        self.m2 = User.objects.create_user("merchant2", password="merchant-pass")
        self.c1 = User.objects.create_user("customer1", password="customer-pass")
        self.c2 = User.objects.create_user("customer2", password="customer-pass")
        self.admin = User.objects.create_superuser("admin", "admin@example.test", "admin-pass")
        for user, role in [(self.m1, "lojista"), (self.m2, "lojista"), (self.c1, "cliente"), (self.c2, "cliente")]:
            Perfil.objects.create(user=user, papel=role)
        self.l1 = Loja.objects.create(dono=self.m1, nome="Loja A", whatsapp="111", aberta=True, ativa=True, assinatura_status="ativa")
        self.l2 = Loja.objects.create(dono=self.m2, nome="Loja B", whatsapp="222", aberta=True, ativa=True, assinatura_status="ativa")
        # This fixture deliberately models two custom delivery areas.
        AreaEntrega.objects.all().delete()
        self.cat1 = Categoria.objects.create(loja=self.l1, nome="A")
        self.cat2 = Categoria.objects.create(loja=self.l2, nome="B")
        self.p1 = Produto.objects.create(loja=self.l1, categoria=self.cat1, nome="Arroz", preco="10.00")
        self.p2 = Produto.objects.create(loja=self.l2, categoria=self.cat2, nome="Cafe", preco="4.50")
        self.area1 = AreaEntrega.objects.create(loja=self.l1, condominio="Reserva", taxa="3.50")
        self.area2 = AreaEntrega.objects.create(loja=self.l2, condominio="Reserva", taxa="1.00")
        self.addr1 = Endereco.objects.create(cliente=self.c1, condominio="Reserva", bloco="A", apartamento="101", destinatario="Cliente 1", telefone="111")
        self.addr2 = Endereco.objects.create(cliente=self.c2, condominio="Reserva", bloco="B", apartamento="202", destinatario="Cliente 2", telefone="222")
        self.client.force_authenticate(self.c1)

    def add(self, loja=None, produto=None, quantidade=2):
        loja = loja or self.l1
        produto = produto or self.p1
        return self.client.post(f"/api/carrinhos/{loja.pk}/itens/", {"produto": produto.pk, "quantidade": quantidade}, format="json")

    def payload(self, **changes):
        return {"loja": self.l1.pk, "endereco": self.addr1.pk, "area_entrega": self.area1.pk, "meio_pagamento": "pix", **changes}

    def order(self):
        self.client.force_authenticate(self.c1)
        self.assertEqual(self.add().status_code, 201)
        response = self.client.post("/api/pedidos/", self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["id"]

    def merchant_status(self, pk, status):
        self.client.force_authenticate(self.m1)
        return self.client.post(f"/api/lojista/pedidos/{pk}/transicao/", {"status": status})

    def test_independent_carts_checkout_only_clears_selected_store(self):
        self.assertEqual(self.add().status_code, 201)
        self.assertEqual(self.add(self.l2, self.p2, 3).status_code, 201)
        self.assertEqual(Carrinho.objects.filter(cliente=self.c1).count(), 2)
        response = self.client.post("/api/pedidos/", self.payload())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["total"], "23.50")
        self.assertEqual(response.data["loja"], self.l1.pk)
        self.assertFalse(Carrinho.objects.filter(cliente=self.c1, loja=self.l1).exists())
        remaining = self.client.get(f"/api/carrinhos/{self.l2.pk}/")
        self.assertEqual(remaining.data["subtotal"], "13.50")
        self.assertEqual(remaining.data["itens"][0]["produto"], self.p2.pk)
        second = self.client.post("/api/pedidos/", self.payload(loja=self.l2.pk, area_entrega=self.area2.pk))
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.data["total"], "14.50")
        self.assertEqual(Pedido.objects.count(), 2)

    def test_cross_store_cart_product_rejected_without_changing_carts(self):
        self.assertEqual(self.add().status_code, 201)
        response = self.add(self.l1, self.p2)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(ItemCarrinho.objects.count(), 1)

    def test_cart_quantity_bounds_and_forged_price_rejected(self):
        for qty in [0, -1, 100]:
            self.assertEqual(self.add(quantidade=qty).status_code, 400)
        response = self.client.post(f"/api/carrinhos/{self.l1.pk}/itens/", {"produto": self.p1.pk, "quantidade": 1, "preco": "0.01"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Carrinho.objects.count(), 0)

    def test_cart_add_sets_quantity_and_supports_update_delete(self):
        self.add(quantidade=1)
        response = self.add(quantidade=3)
        self.assertEqual(ItemCarrinho.objects.count(), 1)
        item_id = response.data["itens"][0]["id"]
        url = f"/api/carrinhos/{self.l1.pk}/itens/{item_id}/"
        response = self.client.patch(url, {"quantidade": 5})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["subtotal"], "50.00")
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.delete(f"/api/carrinhos/{self.l1.pk}/").status_code, 204)

    def test_other_customer_cannot_access_cart_items(self):
        self.add()
        item = ItemCarrinho.objects.get()
        self.client.force_authenticate(self.c2)
        self.assertEqual(self.client.get("/api/carrinhos/").data, [])
        url = f"/api/carrinhos/{self.l1.pk}/itens/{item.pk}/"
        self.assertEqual(self.client.patch(url, {"quantidade": 1}).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.client.delete(f"/api/carrinhos/{self.l1.pk}/")
        self.assertTrue(ItemCarrinho.objects.filter(pk=item.pk).exists())

    def test_checkout_uses_fresh_prices_and_delivery_fee(self):
        self.add()
        self.p1.preco = Decimal("12.34")
        self.p1.save()
        self.area1.taxa = Decimal("5.00")
        self.area1.save()
        response = self.client.post("/api/pedidos/", self.payload())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["subtotal"], "24.68")
        self.assertEqual(response.data["taxa_entrega"], "5.00")
        self.assertEqual(response.data["total"], "29.68")
        self.assertEqual(response.data["itens"][0]["preco_unitario"], "12.34")
        self.assertEqual(response.data["pagamento_status"], "pendente")

    def test_order_snapshots_survive_product_address_and_fee_changes(self):
        pk = self.order()
        self.p1.nome = "Changed"
        self.p1.preco = Decimal("99.00")
        self.p1.save()
        self.p1.delete()
        self.addr1.delete()
        self.area1.taxa = Decimal("99.00")
        self.area1.save()
        response = self.client.get(f"/api/pedidos/{pk}/")
        self.assertEqual(response.data["total"], "23.50")
        self.assertEqual(response.data["itens"][0]["nome"], "Arroz")
        self.assertIsNone(response.data["itens"][0]["produto"])
        self.assertEqual(response.data["endereco"]["apartamento"], "101")

    def test_forged_checkout_fields_rejected(self):
        self.add()
        for extra in [{"total": "0.01"}, {"cliente": self.c2.pk}, {"status": "entregue"}, {"pagamento_status": "confirmado"}, {"taxa_entrega": "0"}]:
            self.assertEqual(self.client.post("/api/pedidos/", self.payload(**extra)).status_code, 400)
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertEqual(Carrinho.objects.count(), 1)

    def test_checkout_idempotency_reuses_order_and_preserves_new_cart(self):
        key = str(uuid.uuid4())
        self.add()
        response = self.client.post("/api/pedidos/", self.payload(chave_checkout=key))
        self.assertEqual(response.status_code, 201)
        pk = response.data["id"]
        self.add(quantidade=5)
        repeated = self.client.post("/api/pedidos/", self.payload(chave_checkout=key))
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.data["id"], pk)
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(ItemCarrinho.objects.get().quantidade, 5)
        self.assertEqual(self.client.post("/api/pedidos/", self.payload(chave_checkout=key, loja=self.l2.pk)).status_code, 400)
        self.client.force_authenticate(self.c2)
        self.add()
        other = self.client.post("/api/pedidos/", self.payload(chave_checkout=key, endereco=self.addr2.pk))
        self.assertEqual(other.status_code, 201)
        self.assertNotEqual(other.data["id"], pk)

    def test_duplicate_checkout_does_not_duplicate_order(self):
        self.order()
        self.assertEqual(self.client.post("/api/pedidos/", self.payload()).status_code, 404)
        self.assertEqual(Pedido.objects.count(), 1)

    def test_checkout_other_customer_address_rejected(self):
        self.add()
        self.assertEqual(self.client.post("/api/pedidos/", self.payload(endereco=self.addr2.pk)).status_code, 404)
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertEqual(Carrinho.objects.count(), 1)

    def test_checkout_wrong_area_and_outside_condominium_rejected(self):
        self.add()
        self.assertEqual(self.client.post("/api/pedidos/", self.payload(area_entrega=self.area2.pk)).status_code, 404)
        self.addr1.condominio = "Outro"
        self.addr1.save()
        self.assertEqual(self.client.post("/api/pedidos/", self.payload()).status_code, 400)
        self.assertEqual(Pedido.objects.count(), 0)

    def test_delivery_matching_normalizes_case_and_spaces(self):
        self.addr1.condominio = "  REserVA  "
        self.addr1.save()
        self.order()

    def test_checkout_unaccepted_payment_rejected(self):
        self.add()
        self.assertEqual(self.client.post("/api/pedidos/", self.payload(meio_pagamento="cartao_na_entrega")).status_code, 400)

    def test_unavailable_product_blocks_checkout_without_clearing_cart(self):
        self.add()
        self.p1.ativo = False
        self.p1.save()
        self.assertEqual(self.client.post("/api/pedidos/", self.payload()).status_code, 400)
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertEqual(ItemCarrinho.objects.count(), 1)

    def test_paused_or_expired_subscription_hides_store_and_blocks_new_orders(self):
        self.add()
        for status, until in [("suspensa", None), ("ativa", timezone.localdate() - timedelta(days=1))]:
            self.l1.assinatura_status = status
            self.l1.assinatura_valida_ate = until
            self.l1.save()
            self.assertEqual(self.client.get(f"/api/catalogo/lojas/{self.l1.pk}/").status_code, 404)
            self.assertEqual(self.client.post("/api/pedidos/", self.payload()).status_code, 400)
        self.assertEqual(Carrinho.objects.count(), 1)

    def test_inactive_store_cannot_receive_cart_items(self):
        self.l1.ativa = False
        self.l1.save()
        self.assertEqual(self.add().status_code, 400)

    def test_order_visibility_customer_and_merchant_isolation(self):
        pk = self.order()
        self.client.force_authenticate(self.c2)
        self.assertEqual(self.client.get("/api/pedidos/").data, [])
        self.assertEqual(self.client.get(f"/api/pedidos/{pk}/").status_code, 404)
        self.assertEqual(self.client.post(f"/api/pedidos/{pk}/cancelar/", {}).status_code, 404)
        self.client.force_authenticate(self.m2)
        self.assertEqual(self.client.get("/api/lojista/pedidos/").data, [])
        self.assertEqual(self.client.post(f"/api/lojista/pedidos/{pk}/transicao/", {"status": "aceito"}).status_code, 404)
        self.assertEqual(self.client.post(f"/api/lojista/pedidos/{pk}/pagamento/", {"status": "confirmado"}).status_code, 404)
        self.client.force_authenticate(self.m1)
        self.assertEqual(self.client.get("/api/lojista/pedidos/").data[0]["id"], pk)

    def test_delivery_lifecycle_is_separate_from_payment_and_audited(self):
        pk = self.order()
        for value in ["aceito", "preparando", "saiu_entrega", "entregue"]:
            response = self.merchant_status(pk, value)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["pagamento_status"], "pendente")
        self.assertEqual(EventoPedido.objects.filter(pedido_id=pk, tipo="status").count(), 5)
        self.assertEqual(self.merchant_status(pk, "cancelado").status_code, 400)

    def test_invalid_transition_cannot_skip_states(self):
        pk = self.order()
        self.assertEqual(self.merchant_status(pk, "entregue").status_code, 400)
        self.assertEqual(EventoPedido.objects.filter(pedido_id=pk).count(), 1)
        self.assertEqual(Pedido.objects.get(pk=pk).status, "recebido")

    def test_customer_cancel_only_before_acceptance(self):
        pk = self.order()
        self.assertEqual(self.client.post(f"/api/pedidos/{pk}/cancelar/", {}).status_code, 200)
        self.assertEqual(self.merchant_status(pk, "aceito").status_code, 400)
        pk2 = self.order()
        self.assertEqual(self.merchant_status(pk2, "aceito").status_code, 200)
        self.client.force_authenticate(self.c1)
        self.assertEqual(self.client.post(f"/api/pedidos/{pk2}/cancelar/", {}).status_code, 400)

    def test_customer_reports_payment_merchant_confirms_and_refunds_manually(self):
        pk = self.order()
        response = self.client.post(f"/api/pedidos/{pk}/informar-pagamento/", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["pagamento_status"], "informado")
        self.client.force_authenticate(self.m1)
        url = f"/api/lojista/pedidos/{pk}/pagamento/"
        response = self.client.post(url, {"status": "confirmado"})
        self.assertEqual(response.data["status"], "recebido")
        self.assertEqual(response.data["pagamento_status"], "confirmado")
        self.assertEqual(self.client.post(url, {"status": "estornado"}).status_code, 200)
        self.assertEqual(self.client.post(url, {"status": "confirmado"}).status_code, 400)
        self.assertEqual(EventoPedido.objects.filter(pedido_id=pk, tipo="pagamento").count(), 3)

    def test_customer_cannot_confirm_payment_or_edit_order(self):
        pk = self.order()
        self.assertEqual(self.client.patch(f"/api/pedidos/{pk}/", {"pagamento_status": "confirmado"}).status_code, 405)
        self.assertEqual(self.client.post(f"/api/pedidos/{pk}/informar-pagamento/", {"status": "confirmado"}).status_code, 400)
        self.assertEqual(self.client.post(f"/api/lojista/pedidos/{pk}/pagamento/", {"status": "confirmado"}).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/pedidos/{pk}/").status_code, 405)

    def test_cancellation_does_not_automatically_refund(self):
        pk = self.order()
        self.client.force_authenticate(self.m1)
        self.client.post(f"/api/lojista/pedidos/{pk}/pagamento/", {"status": "confirmado"})
        response = self.merchant_status(pk, "cancelado")
        self.assertEqual(response.data["pagamento_status"], "confirmado")
        self.assertEqual(self.client.post(f"/api/lojista/pedidos/{pk}/pagamento/", {"status": "estornado"}).status_code, 200)

    def test_payment_on_cancelled_order_and_unpaid_refund_rejected(self):
        pk = self.order()
        self.client.force_authenticate(self.m1)
        self.assertEqual(self.client.post(f"/api/lojista/pedidos/{pk}/pagamento/", {"status": "estornado"}).status_code, 400)
        self.merchant_status(pk, "cancelado")
        self.assertEqual(self.client.post(f"/api/lojista/pedidos/{pk}/pagamento/", {"status": "confirmado"}).status_code, 400)

    def test_paused_store_can_complete_existing_orders(self):
        pk = self.order()
        self.l1.assinatura_status = "suspensa"
        self.l1.save()
        self.assertEqual(self.merchant_status(pk, "aceito").status_code, 200)

    def test_store_with_order_cannot_be_deleted(self):
        self.order()
        self.client.force_authenticate(self.m1)
        self.assertEqual(self.client.delete(f"/api/lojas/{self.l1.pk}/").status_code, 400)
        self.assertTrue(Loja.objects.filter(pk=self.l1.pk).exists())

    def test_addresses_are_owned_and_owner_cannot_be_forged(self):
        self.assertEqual(self.client.get(f"/api/enderecos/{self.addr2.pk}/").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/enderecos/{self.addr2.pk}/", {"bloco": "X"}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/enderecos/{self.addr2.pk}/").status_code, 404)
        payload = {"condominio": "Reserva", "bloco": "C", "apartamento": "303", "destinatario": "Cliente", "telefone": "123"}
        self.assertEqual(self.client.post("/api/enderecos/", {**payload, "cliente": self.c2.pk}).status_code, 400)
        self.assertEqual(self.client.post("/api/enderecos/", payload).status_code, 201)

    def test_merchant_delivery_areas_are_isolated_and_validated(self):
        self.client.force_authenticate(self.m1)
        self.assertEqual(self.client.get(f"/api/lojista/areas-entrega/{self.area2.pk}/").status_code, 404)
        self.assertEqual(self.client.post("/api/lojista/areas-entrega/", {"condominio": "  RESERVA ", "taxa": "2"}).status_code, 400)
        self.assertEqual(self.client.post("/api/lojista/areas-entrega/", {"condominio": "Outro", "taxa": "-1"}).status_code, 400)
        self.assertEqual(self.client.patch(f"/api/lojista/areas-entrega/{self.area1.pk}/", {"loja": self.l2.pk}).status_code, 400)
        response = self.client.post("/api/lojista/areas-entrega/", {"condominio": "Outro", "taxa": "0"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["loja"], self.l1.pk)

    def test_public_catalog_hides_private_and_inactive_data(self):
        self.client.force_authenticate(None)
        response = self.client.get(f"/api/catalogo/lojas/{self.l1.pk}/")
        self.assertEqual(response.status_code, 200)
        for field in ["dono", "mensalidade", "assinatura_status"]:
            self.assertNotIn(field, response.data)
        self.assertEqual(self.client.get(f"/api/catalogo/lojas/{self.l1.pk}/produtos/").data[0]["id"], self.p1.pk)
        self.p1.ativo = False
        self.p1.save()
        self.assertEqual(self.client.get(f"/api/catalogo/lojas/{self.l1.pk}/produtos/").data, [])
        self.assertEqual(self.client.get(f"/api/catalogo/lojas/{self.l1.pk}/areas-entrega/").data[0]["taxa"], "3.50")

    def test_only_admin_controls_subscription_without_default_price(self):
        self.client.force_authenticate(self.m1)
        for changes in [{"ativa": True}, {"assinatura_status": "ativa"}, {"mensalidade": "0"}]:
            self.assertEqual(self.client.patch(f"/api/lojas/{self.l1.pk}/", changes).status_code, 400)
        self.assertEqual(self.client.patch(f"/api/administracao/lojas/{self.l1.pk}/", {"ativa": False}).status_code, 403)
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f"/api/administracao/lojas/{self.l1.pk}/", {"ativa": False, "assinatura_status": "suspensa"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["mensalidade"])
        self.assertEqual(self.client.patch(f"/api/administracao/lojas/{self.l1.pk}/", {"mensalidade": "-1"}).status_code, 400)
        self.assertEqual(self.client.patch(f"/api/administracao/lojas/{self.l1.pk}/", {"dono": self.m2.pk}).status_code, 400)
        self.assertEqual(self.client.get("/api/administracao/usuarios/").status_code, 200)

    def test_profile_boundaries_and_clients_have_no_subscription(self):
        response = self.client.get("/api/conta/")
        self.assertEqual(response.data["papel"], "cliente")
        self.assertNotIn("mensalidade", response.data)
        for changes in [{"papel": "administrador"}, {"is_staff": True}, {"is_superuser": True}]:
            self.assertEqual(self.client.patch("/api/conta/", changes).status_code, 400)
        self.assertEqual(self.client.post("/api/lojas/", {"nome": "invaded", "whatsapp": "111"}).status_code, 403)
        self.assertEqual(self.client.get("/api/lojista/pedidos/").status_code, 403)
        self.assertEqual(self.client.get("/api/administracao/lojas/").status_code, 403)
        self.client.force_authenticate(self.m1)
        self.assertEqual(self.client.get("/api/enderecos/").status_code, 403)
        self.assertEqual(self.client.get("/api/pedidos/").status_code, 403)
        self.assertEqual(self.client.get("/api/carrinhos/").status_code, 403)

    def test_store_payment_methods_configuration(self):
        self.client.force_authenticate(self.m1)
        url = f"/api/lojas/{self.l1.pk}/"
        for value in [[], ["automatic_charge"], ["pix", "pix"], "pix"]:
            self.assertEqual(self.client.patch(url, {"meios_pagamento": value}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"meios_pagamento": ["dinheiro"]}, format="json").status_code, 200)

    def test_anonymous_cannot_access_private_endpoints(self):
        self.client.force_authenticate(None)
        for path in ["/api/conta/", "/api/enderecos/", "/api/carrinhos/", "/api/pedidos/", "/api/lojista/pedidos/", "/api/administracao/lojas/"]:
            self.assertEqual(self.client.get(path).status_code, 401)


class RegistrationTests(APITestCase):
    def payload(self, **changes):
        return {"username": "new-user", "password": "safe-unrelated-pass-936!", "email": "person@example.test", "first_name": "Pessoa", "telefone": "85999999999", **changes}

    def test_registration_never_grants_admin_flags(self):
        for extra in [{"papel": "administrador"}, {"is_staff": True}, {"is_superuser": True}, {"is_active": True}]:
            self.assertEqual(self.client.post("/api/auth/cadastro/", self.payload(**extra)).status_code, 400)
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_customer_signup_and_jwt_login(self):
        response = self.client.post("/api/auth/cadastro/", self.payload())
        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get()
        self.assertEqual(user.perfil.papel, "cliente")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(self.client.post("/api/token/", {"username": "new-user", "password": "safe-unrelated-pass-936!"}).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/cadastro/", self.payload(username="NEW-USER")).status_code, 400)

    def test_merchant_signup_store_remains_pending_until_admin_approval(self):
        self.assertEqual(self.client.post("/api/auth/cadastro/", self.payload(papel="lojista")).status_code, 201)
        user = get_user_model().objects.get()
        self.client.force_authenticate(user)
        response = self.client.post("/api/lojas/", {"nome": "Nova loja", "whatsapp": "111"})
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.data["ativa"])
        self.assertEqual(response.data["assinatura_status"], "pendente")
        self.assertIsNone(response.data["mensalidade"])
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/catalogo/lojas/").data, [])

    def test_weak_password_rejected(self):
        self.assertEqual(self.client.post("/api/auth/cadastro/", self.payload(password="123")).status_code, 400)


class AuthenticationSecurityTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("secure-user", password="original-safe-9942!")
        Perfil.objects.create(user=self.user, papel="cliente")

    def login(self):
        response = self.client.post("/api/token/", {"username": self.user.username, "password": "original-safe-9942!"})
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_password_change_revokes_all_existing_access_and_refresh_tokens(self):
        first = self.login()
        second = self.login()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + first["access"])
        response = self.client.post("/api/conta/senha/", {"senha_atual": "original-safe-9942!", "nova_senha": "replacement-strong-8532!"})
        self.assertEqual(response.status_code, 200)
        for pair in [first, second]:
            self.client.credentials(HTTP_AUTHORIZATION="Bearer " + pair["access"])
            self.assertEqual(self.client.get("/api/conta/").status_code, 401)
            self.assertEqual(self.client.post("/api/token/refresh/", {"refresh": pair["refresh"]}).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post("/api/token/", {"username": self.user.username, "password": "original-safe-9942!"}).status_code, 401)
        self.assertEqual(self.client.post("/api/token/", {"username": self.user.username, "password": "replacement-strong-8532!"}).status_code, 200)

    def test_password_change_requires_current_password_and_valid_new_password(self):
        pair = self.login()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + pair["access"])
        for attrs in [{"senha_atual": "wrong", "nova_senha": "valid-password-995!"},
                      {"senha_atual": "original-safe-9942!", "nova_senha": "123"}]:
            self.assertEqual(self.client.post("/api/conta/senha/", attrs).status_code, 400)
        self.assertEqual(self.client.get("/api/conta/").status_code, 200)

    def test_admin_password_reset_invalidates_old_tokens(self):
        pair = self.login()
        self.user.set_password("admin-replaced-safe-6621!")
        self.user.save()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + pair["access"])
        self.assertEqual(self.client.get("/api/conta/").status_code, 401)
        self.assertEqual(self.client.post("/api/token/refresh/", {"refresh": pair["refresh"]}).status_code, 401)
        self.assertEqual(self.client.post("/api/token/verify/", {"token": pair["access"]}).status_code, 401)

    def test_deactivated_user_cannot_use_old_tokens_or_login(self):
        pair = self.login()
        self.user.is_active = False
        self.user.save()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + pair["access"])
        self.assertEqual(self.client.get("/api/conta/").status_code, 401)
        self.assertEqual(self.client.post("/api/token/refresh/", {"refresh": pair["refresh"]}).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post("/api/token/", {"username": self.user.username, "password": "original-safe-9942!"}).status_code, 401)

    def test_deleted_user_refresh_is_rejected_without_server_error(self):
        pair = self.login()
        self.user.delete()
        self.assertEqual(self.client.post("/api/token/refresh/", {"refresh": pair["refresh"]}).status_code, 401)

    def test_admin_privileges_are_checked_in_database_for_every_request(self):
        self.user.is_staff = True
        self.user.save()
        pair = self.login()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + pair["access"])
        self.assertEqual(self.client.get("/api/administracao/lojas/").status_code, 200)
        self.user.is_staff = False
        self.user.save()
        self.assertEqual(self.client.get("/api/administracao/lojas/").status_code, 403)

    def test_expired_tampered_and_wrong_type_tokens_rejected(self):
        import base64
        import json
        from rest_framework_simplejwt.tokens import RefreshToken
        pair = self.login()
        pieces = pair["access"].split(".")
        payload = json.loads(base64.urlsafe_b64decode(pieces[1] + "=="))
        payload["user_id"] = 999999
        payload["is_staff"] = True
        pieces[1] = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        expired = RefreshToken.for_user(self.user).access_token
        expired.set_exp(lifetime=timedelta(seconds=-1))
        for token in [".".join(pieces), str(expired), pair["refresh"], "invalid"]:
            self.client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
            self.assertEqual(self.client.get("/api/conta/").status_code, 401)

    def test_login_rate_limit(self):
        from django.core.cache import cache
        from unittest.mock import patch
        from rest_framework.throttling import ScopedRateThrottle
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"auth_login": "2/min"}):
            cache.clear()
            for _ in range(2):
                self.assertEqual(self.client.post("/api/token/", {"username": "unknown", "password": "wrong"}).status_code, 401)
            response = self.client.post("/api/token/", {"username": "unknown", "password": "wrong"})
            self.assertEqual(response.status_code, 429)
            self.assertIn("Retry-After", response)
            cache.clear()


class RealJWTIsolationTests(APITestCase):
    setUp = MarketplaceTests.setUp
    order = MarketplaceTests.order
    add = MarketplaceTests.add
    payload = MarketplaceTests.payload
    # Exercise these separately with authenticated HTTP headers instead of force_authenticate.
    def test_real_customer_and_merchant_tokens_preserve_object_isolation(self):
        pk = self.order()
        self.client.force_authenticate(None)
        pair = self.client.post("/api/token/", {"username": "customer2", "password": "customer-pass"}).data
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + pair["access"])
        self.assertEqual(self.client.get("/api/conta/").data["papel"], "cliente")
        self.assertEqual(self.client.get(f"/api/pedidos/{pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/enderecos/{self.addr1.pk}/").status_code, 404)
        pair = self.client.post("/api/token/", {"username": "merchant2", "password": "merchant-pass"}).data
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + pair["access"])
        self.assertEqual(self.client.get(f"/api/lojas/{self.l1.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/produtos/{self.p1.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/lojista/pedidos/{pk}/").status_code, 404)
