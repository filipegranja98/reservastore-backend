from rest_framework.test import APITestCase
from . import tests as fixtures

class CashChangeTests(APITestCase):
    setUp=fixtures.MarketplaceTests.setUp
    add=fixtures.MarketplaceTests.add
    payload=fixtures.MarketplaceTests.payload

    def test_cash_change_includes_delivery_and_is_recorded_for_merchant(self):
        self.add()
        data=self.payload(meio_pagamento="dinheiro",precisa_troco=True,troco_para="50.00")
        preview=self.client.post("/api/pedidos/previa/",data,format="json")
        self.assertEqual(preview.status_code,200,preview.data)
        self.assertEqual(preview.data["valor_troco"],"26.50")
        response=self.client.post("/api/pedidos/",data,format="json")
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data["troco_para"],"50.00")
        self.client.force_authenticate(self.m1)
        detail=self.client.get(f'/api/lojista/pedidos/{response.data["id"]}/').data
        self.assertEqual(detail["valor_troco"],"26.50")
        self.assertEqual(detail["pagamento_status"],"pendente")

    def test_cash_without_change_and_invalid_combinations(self):
        self.add()
        for changes in [dict(precisa_troco=True),dict(precisa_troco=True,troco_para="20.00"),dict(precisa_troco=False,troco_para="50.00")]:
            response=self.client.post("/api/pedidos/previa/",self.payload(meio_pagamento="dinheiro",**changes),format="json")
            self.assertEqual(response.status_code,400,response.data)
        response=self.client.post("/api/pedidos/previa/",self.payload(meio_pagamento="dinheiro",precisa_troco=False),format="json")
        self.assertEqual(response.status_code,200)
        self.assertIsNone(response.data["valor_troco"])
        self.assertEqual(self.client.post("/api/pedidos/previa/",self.payload(precisa_troco=True,troco_para="50.00"),format="json").status_code,400)

    def test_credit_and_debit_must_be_enabled_by_owner(self):
        self.add()
        for method in ["credito","debito"]:
            self.assertEqual(self.client.post("/api/pedidos/previa/",self.payload(meio_pagamento=method),format="json").status_code,400)
        self.client.force_authenticate(self.m1)
        self.assertEqual(self.client.patch(f"/api/lojas/{self.l1.pk}/",{"meios_pagamento":["credito","debito"]},format="json").status_code,200)
        self.client.force_authenticate(self.c1)
        for method in ["credito","debito"]:
            self.assertEqual(self.client.post("/api/pedidos/previa/",self.payload(meio_pagamento=method),format="json").status_code,200)

    def test_pickup_change_has_no_delivery_fee(self):
        self.l1.permite_retirada=True;self.l1.save(update_fields=["permite_retirada"])
        self.add()
        response=self.client.post("/api/pedidos/previa/",{"loja":self.l1.pk,"modalidade":"retirada","meio_pagamento":"dinheiro","precisa_troco":True,"troco_para":"20.00"},format="json")
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(response.data["valor_troco"],"0.00")
