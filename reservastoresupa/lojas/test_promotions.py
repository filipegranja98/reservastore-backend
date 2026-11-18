from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APITestCase
from reservastoresupa.marketplace import tests as fixtures
from reservastoresupa.lojas.models import Promocao

class PromotionTests(APITestCase):
    setUp=fixtures.MarketplaceTests.setUp
    add=fixtures.MarketplaceTests.add
    payload=fixtures.MarketplaceTests.payload

    def create_promo(self,**extra):
        self.client.force_authenticate(self.m1)
        return self.client.post('/api/promocoes/',{'titulo':'Oferta da semana','descricao':'Arroz com desconto','validade':str(timezone.localdate()+timedelta(days=2)),**extra},format='json')

    def test_owner_can_create_edit_deactivate_and_foreign_store_is_blocked(self):
        response=self.create_promo()
        self.assertEqual(response.status_code,201,response.data)
        path=f"/api/promocoes/{response.data['id']}/"
        self.client.force_authenticate(self.m2)
        self.assertEqual(self.client.patch(path,{'titulo':'Invadido'},format='json').status_code,404)
        self.client.force_authenticate(self.c1)
        self.assertEqual(self.client.get('/api/promocoes/').data,[])
        self.assertEqual(self.client.post('/api/promocoes/',{'titulo':'Não pode'},format='json').status_code,404)
        self.client.force_authenticate(self.m1)
        self.assertEqual(self.client.patch(path,{'ativa':False},format='json').status_code,200)
        self.assertEqual(self.client.get(f'/api/catalogo/lojas/{self.l1.pk}/promocoes/').data,[])

    def test_public_only_returns_current_active_promotions_of_public_store(self):
        current=self.create_promo()
        Promocao.objects.create(loja=self.l1,titulo='Vencida',validade=timezone.localdate()-timedelta(days=1))
        Promocao.objects.create(loja=self.l1,titulo='Desativada',validade=timezone.localdate(),ativa=False)
        Promocao.objects.create(loja=self.l2,titulo='Outra loja',validade=timezone.localdate())
        self.client.force_authenticate(None)
        rows=self.client.get(f'/api/catalogo/lojas/{self.l1.pk}/promocoes/').data
        self.assertEqual([p['id'] for p in rows],[current.data['id']])
        self.l1.ativa=False;self.l1.save()
        self.assertEqual(self.client.get(f'/api/catalogo/lojas/{self.l1.pk}/promocoes/').status_code,404)

    def test_product_discount_matches_catalog_cart_preview_and_final_order(self):
        promo=self.create_promo(produto=self.p1.pk,preco_promocional='7.50')
        self.assertEqual(promo.status_code,201,promo.data)
        self.assertEqual(promo.data['preco_anterior'],'10.00')
        self.client.force_authenticate(self.c1)
        self.assertEqual(self.client.get(f'/api/catalogo/lojas/{self.l1.pk}/produtos/').data[0]['preco'],'7.50')
        self.assertEqual(self.add().data['subtotal'],'15.00')
        preview=self.client.post('/api/pedidos/previa/',self.payload(),format='json')
        self.assertEqual(preview.data['subtotal'],'15.00')
        ordered=self.client.post('/api/pedidos/',self.payload(),format='json')
        self.assertEqual(ordered.status_code,201,ordered.data)
        self.assertEqual(ordered.data['subtotal'],'15.00')
        Promocao.objects.filter(pk=promo.data['id']).update(ativa=False)
        self.assertEqual(self.client.get(f"/api/pedidos/{ordered.data['id']}/").data['subtotal'],'15.00')

    def test_expiration_or_deactivation_revalidates_checkout_price(self):
        promo=self.create_promo(produto=self.p1.pk,preco_promocional='7.50')
        self.client.force_authenticate(self.c1);self.add()
        self.assertEqual(self.client.post('/api/pedidos/previa/',self.payload(),format='json').data['subtotal'],'15.00')
        Promocao.objects.filter(pk=promo.data['id']).update(validade=timezone.localdate()-timedelta(days=1))
        self.assertEqual(self.client.get(f'/api/carrinhos/{self.l1.pk}/').data['subtotal'],'20.00')
        self.assertEqual(self.client.post('/api/pedidos/previa/',self.payload(),format='json').data['subtotal'],'20.00')

    def test_bad_foreign_duplicate_and_inflated_discount_are_rejected(self):
        for fields in [{'produto':self.p2.pk,'preco_promocional':'1.00'},{'produto':self.p1.pk,'preco_promocional':'11.00'},{'produto':self.p1.pk,'preco_promocional':'0'},{'preco_promocional':'1.00'},{'validade':str(timezone.localdate()-timedelta(days=1))},{'loja':self.l2.pk}]:
            self.assertEqual(self.create_promo(**fields).status_code,400,fields)
        self.assertEqual(self.create_promo(produto=self.p1.pk,preco_promocional='7').status_code,201)
        self.assertEqual(self.create_promo(produto=self.p1.pk,preco_promocional='8').status_code,400)

    def test_services_only_allow_descriptive_offers(self):
        self.l1.modalidade_catalogo='servicos';self.l1.save()
        self.assertEqual(self.create_promo(descricao='Desconto em sofá e cadeiras').status_code,201)
        self.assertEqual(self.create_promo(produto=self.p1.pk,preco_promocional='1').status_code,400)

    def test_image_upload_is_normalized_and_can_be_removed(self):
        self.client.force_authenticate(self.m1)
        output=BytesIO();Image.new('RGB',(20,10),'green').save(output,'PNG')
        response=self.client.post('/api/promocoes/',{'titulo':'Imagem','validade':str(timezone.localdate()),'imagem':SimpleUploadedFile('image.png',output.getvalue(),content_type='image/png'),'produto':'','preco_promocional':''},format='multipart')
        self.assertEqual(response.status_code,201,response.data)
        item=Promocao.objects.get(pk=response.data['id'])
        with item.imagem.open('rb') as photo: self.assertEqual(Image.open(photo).format,'JPEG')
        removed=self.client.patch(f'/api/promocoes/{item.pk}/',{'imagem':None},format='json')
        self.assertIsNone(removed.data['imagem'])
