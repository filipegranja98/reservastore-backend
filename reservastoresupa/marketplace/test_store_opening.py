import uuid
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from reservastoresupa.lojas.models import Loja
from . import tests as fixtures
from .models import Carrinho, ItemCarrinho, Pedido


class StoreOpeningTests(APITestCase):
    setUp = fixtures.MarketplaceTests.setUp
    add = fixtures.MarketplaceTests.add
    payload = fixtures.MarketplaceTests.payload

    def test_stores_start_closed_until_operation_is_explicitly_enabled(self):
        owner=get_user_model().objects.create_user(username='new-closed-owner')
        shop=Loja.objects.create(dono=owner,nome='New closed',whatsapp='000',ativa=True,assinatura_status='ativa')
        self.assertFalse(shop.aberta)
        self.assertFalse(shop.aceita_pedidos)

    def test_closed_store_and_its_catalog_remain_public(self):
        self.l1.aberta=False
        self.l1.save(update_fields=['aberta'])
        self.client.force_authenticate(None)
        stores=self.client.get('/api/catalogo/lojas/').data
        self.assertEqual(len(stores),2)
        self.assertFalse(next(shop for shop in stores if shop['id']==self.l1.pk)['aberta'])
        self.assertTrue(next(shop for shop in stores if shop['id']==self.l2.pk)['aberta'])
        self.assertEqual(self.client.get(f'/api/catalogo/lojas/{self.l1.pk}/produtos/').status_code,200)

    def test_only_owner_changes_operational_state_and_boolean_is_validated(self):
        self.assertEqual(self.client.patch(f'/api/lojas/{self.l1.pk}/',{'aberta':False},format='json').status_code,404)
        self.client.force_authenticate(self.m1)
        self.assertEqual(self.client.patch(f'/api/lojas/{self.l1.pk}/',{'aberta':False},format='json').status_code,200)
        self.assertEqual(self.client.patch(f'/api/lojas/{self.l2.pk}/',{'aberta':False},format='json').status_code,404)
        self.assertEqual(self.client.patch(f'/api/lojas/{self.l1.pk}/',{'aberta':'open-now'},format='json').status_code,400)
        self.assertEqual(self.client.patch(f'/api/lojas/{self.l1.pk}/',{'aberta':True},format='json').status_code,200)

    def test_closing_after_preview_blocks_new_purchase_and_preserves_all_carts(self):
        self.assertEqual(self.add().status_code,201)
        self.assertEqual(self.add(self.l2,self.p2,3).status_code,201)
        self.assertEqual(self.client.post('/api/pedidos/previa/',self.payload(),format='json').status_code,200)
        before=list(ItemCarrinho.objects.values_list('id','quantidade'))
        Loja.objects.filter(pk=self.l1.pk).update(aberta=False)
        self.assertEqual(self.add().status_code,400)
        self.assertEqual(self.client.post('/api/pedidos/previa/',self.payload(),format='json').status_code,400)
        self.assertEqual(self.client.post('/api/pedidos/',self.payload(chave_checkout=str(uuid.uuid4())),format='json').status_code,400)
        self.assertEqual(before,list(ItemCarrinho.objects.values_list('id','quantidade')))
        self.assertEqual(Pedido.objects.count(),0)
        self.assertEqual(Carrinho.objects.count(),2)

    def test_closed_store_still_allows_replay_and_processing_of_existing_order(self):
        self.add()
        body=self.payload(chave_checkout=str(uuid.uuid4()))
        original=self.client.post('/api/pedidos/',body,format='json')
        self.assertEqual(original.status_code,201)
        self.add()
        Loja.objects.filter(pk=self.l1.pk).update(aberta=False)
        replay=self.client.post('/api/pedidos/',body,format='json')
        self.assertEqual(replay.status_code,200)
        self.assertEqual(replay.data['id'],original.data['id'])
        self.assertEqual(Pedido.objects.count(),1)
        self.assertEqual(ItemCarrinho.objects.get(carrinho__cliente=self.c1,carrinho__loja=self.l1).quantidade,2)
        self.client.force_authenticate(self.m1)
        self.assertEqual(self.client.post(f"/api/lojista/pedidos/{original.data['id']}/transicao/",{'status':'aceito'},format='json').status_code,200)
