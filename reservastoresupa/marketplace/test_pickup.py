import uuid
from rest_framework.test import APITestCase
from . import tests as fixtures
from .models import AreaEntrega, Endereco, Pedido
from reservastoresupa.lojas.models import TipoLoja

class PickupTests(APITestCase):
    def setUp(self):
        fixtures.MarketplaceTests.setUp(self)
        self.l1.permite_retirada = True
        self.l1.save(update_fields=["permite_retirada"])
    add = fixtures.MarketplaceTests.add
    merchant_status = fixtures.MarketplaceTests.merchant_status

    def pickup(self):
        return {"loja":self.l1.pk,"modalidade":"retirada","meio_pagamento":"pix","chave_checkout":str(uuid.uuid4())}

    def test_pickup_without_address_or_delivery_area_has_zero_fee_and_replays(self):
        self.add()
        Endereco.objects.all().delete()
        AreaEntrega.objects.all().delete()
        data=self.pickup()
        preview=self.client.post("/api/pedidos/previa/",{k:v for k,v in data.items() if k != "chave_checkout"},format="json")
        self.assertEqual(preview.status_code,200,preview.data)
        self.assertIsNone(preview.data["endereco"])
        self.assertEqual(preview.data["taxa_entrega"],"0.00")
        response=self.client.post("/api/pedidos/",data,format="json")
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data["total"],"20.00")
        self.assertEqual(response.data["modalidade"],"retirada")
        self.assertEqual(self.client.post("/api/pedidos/",data,format="json").data["id"],response.data["id"])
        self.assertEqual(Pedido.objects.count(),1)

    def test_pickup_lifecycle_cannot_be_sent_for_delivery(self):
        self.add()
        pk=self.client.post("/api/pedidos/",self.pickup(),format="json").data["id"]
        for state in ["aceito","preparando"]:
            self.assertEqual(self.merchant_status(pk,state).status_code,200)
        self.assertEqual(self.merchant_status(pk,"saiu_entrega").status_code,400)
        self.assertEqual(self.merchant_status(pk,"pronto_retirada").status_code,200)
        self.assertEqual(self.merchant_status(pk,"entregue").status_code,200)

    def test_delivery_requires_address_and_services_cannot_use_pickup(self):
        self.add()
     self.assertEqual(self.client.post("/api/pedidos/",{"loja":self.l1.pk,"meio_pagamento":"pix"},format="json").status_code,400)
        kind=TipoLoja.objects.create(nome="Service",modo_catalogo="servicos")
        self.l1.tipo_loja=kind
        self.l1.save(update_fields=["tipo_loja"])
        self.assertEqual(self.client.post("/api/pedidos/",self.pickup(),format="json").status_code,400)

    def test_pickup_rejects_forged_address_and_fee(self):
        self.add()
        for fields in [{"endereco":self.addr2.pk},{"taxa_entrega":"0.01"}]:
            self.assertEqual(self.client.post("/api/pedidos/",{**self.pickup(),**fields},format="json").status_code,400)

    def test_merchant_controls_modes_and_checkout_rechecks(self):
        self.add()
        self.client.force_authenticate(self.m2)
        self.assertEqual(self.client.patch(f"/api/lojas/{self.l1.pk}/",{"permite_retirada":False},format="json").status_code,404)
        self.client.force_authenticate(self.m1)
        self.assertEqual(self.client.patch(f"/api/lojas/{self.l1.pk}/",{"permite_retirada":False,"permite_entrega":False},format="json").status_code,200)
        self.client.force_authenticate(self.c1)
        self.assertEqual(self.client.post("/api/pedidos/",self.pickup(),format="json").status_code,400)
        self.assertEqual(self.client.post("/api/pedidos/",{"loja":self.l1.pk,"endereco":self.addr1.pk,"area_entrega":self.area1.pk,"meio_pagamento":"pix"},format="json").status_code,400)
