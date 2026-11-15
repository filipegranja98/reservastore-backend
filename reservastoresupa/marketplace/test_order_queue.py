from rest_framework.test import APITestCase
from . import tests as fixtures

class MerchantQueueTests(APITestCase):
    setUp=fixtures.MarketplaceTests.setUp
    add=fixtures.MarketplaceTests.add
    payload=fixtures.MarketplaceTests.payload
    order=fixtures.MarketplaceTests.order
    merchant_status=fixtures.MarketplaceTests.merchant_status

    def test_active_queue_oldest_first_and_owner_isolation(self):
        first=self.order()
        second=self.order()
        self.client.force_authenticate(self.m1)
        response=self.client.get("/api/lojista/pedidos/?fila=ativos&ordem=antigos&page=1&page_size=20")
        self.assertEqual([item["id"] for item in response.data["results"]],[first,second])
        self.assertEqual(self.merchant_status(first,"cancelado").status_code,200)
        response=self.client.get("/api/lojista/pedidos/?fila=ativos&ordem=antigos&page=1&page_size=20")
        self.assertEqual([item["id"] for item in response.data["results"]],[second])
        self.client.force_authenticate(self.m2)
        self.assertEqual(self.client.get("/api/lojista/pedidos/?fila=ativos&page=1").data["count"],0)

    def test_preparation_event_is_returned_with_client_details(self):
        pk=self.order()
        self.merchant_status(pk,"aceito")
        self.merchant_status(pk,"preparando")
        data=self.client.get(f"/api/lojista/pedidos/{pk}/").data
        event=next(item for item in data["eventos"] if item["tipo"]=="status" and item["novo"]=="preparando")
        self.assertTrue(event["criado_em"])
        self.assertEqual(data["itens"][0]["quantidade"],2)
        self.assertEqual(data["endereco"]["apartamento"],"101")
