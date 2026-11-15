from rest_framework.test import APITestCase
from . import tests as fixtures
from .models import EventoPedido

class CustomerReceiptTests(APITestCase):
    setUp=fixtures.MarketplaceTests.setUp
    add=fixtures.MarketplaceTests.add
    payload=fixtures.MarketplaceTests.payload
    order=fixtures.MarketplaceTests.order
    merchant_status=fixtures.MarketplaceTests.merchant_status

    def confirm(self,pk):
        self.client.force_authenticate(self.c1)
        return self.client.post(f"/api/pedidos/{pk}/confirmar-recebimento/",{},format="json")

    def test_customer_confirms_delivery_once_with_author_and_payment_unchanged(self):
        pk=self.order()
        for state in ["aceito","preparando","saiu_entrega"]:
            self.assertEqual(self.merchant_status(pk,state).status_code,200)
        response=self.confirm(pk)
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data["status"],"entregue")
        self.assertEqual(response.data["pagamento_status"],"pendente")
        self.assertEqual(self.confirm(pk).status_code,200)
        events=EventoPedido.objects.filter(pedido_id=pk,novo="entregue",tipo="status")
        self.assertEqual(events.count(),1)
        self.assertEqual(events.get().autor_id,self.c1.pk)
        self.client.force_authenticate(self.m1)
        self.assertEqual(self.client.get(f"/api/lojista/pedidos/{pk}/").data["status"],"entregue")

    def test_customer_cannot_confirm_early_canceled_or_foreign_orders(self):
        pk=self.order()
        self.assertEqual(self.confirm(pk).status_code,400)
        self.client.force_authenticate(self.c2)
        self.assertEqual(self.client.post(f"/api/pedidos/{pk}/confirmar-recebimento/",{}).status_code,404)
        self.merchant_status(pk,"cancelado")
        self.assertEqual(self.confirm(pk).status_code,400)

    def test_customer_can_confirm_pickup_when_ready(self):
        self.l1.permite_retirada=True
        self.l1.save(update_fields=["permite_retirada"])
        self.add()
        response=self.client.post("/api/pedidos/",{"loja":self.l1.pk,"modalidade":"retirada","meio_pagamento":"pix"},format="json")
        pk=response.data["id"]
        for state in ["aceito","preparando","pronto_retirada"]:
            self.assertEqual(self.merchant_status(pk,state).status_code,200)
        self.assertEqual(self.confirm(pk).status_code,200)
