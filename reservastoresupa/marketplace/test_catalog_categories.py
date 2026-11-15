from rest_framework.test import APITestCase
from django.db.models.deletion import ProtectedError
from reservastoresupa.lojas.models import TipoLoja, Categoria, Produto
from . import tests as fixtures


class CatalogCategoryTests(APITestCase):
    setUp = fixtures.MarketplaceTests.setUp

    def test_store_types_are_public_read_only_and_filter_before_pagination(self):
        kind=TipoLoja.objects.create(nome='Mercado')
        self.l1.tipo_loja=kind
        self.l1.save(update_fields=['tipo_loja'])
        self.client.force_authenticate(None)
        response=self.client.get('/api/catalogo/tipos-loja/',{'page':1,'page_size':1})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['results'],[{'id':kind.pk,'nome':'Mercado','modo_catalogo':'produtos'}])
        self.assertEqual(self.client.post('/api/catalogo/tipos-loja/',{'nome':'Unauthorized'}).status_code,405)
        stores=self.client.get('/api/catalogo/lojas/',{'tipo_loja':kind.pk,'page':1,'page_size':1}).data
        self.assertEqual(stores['count'],1)
        self.assertEqual(stores['results'][0]['id'],self.l1.pk)
        self.assertEqual(stores['results'][0]['tipo_loja_nome'],'Mercado')
        self.assertEqual(self.client.get('/api/catalogo/lojas/',{'tipo_loja':'abc','page':1}).status_code,400)
        with self.assertRaises(ProtectedError):kind.delete()

    def test_public_product_category_filter_is_scoped_to_store(self):
        second=Categoria.objects.create(loja=self.l1,nome='Outra categoria')
        product=Produto.objects.create(loja=self.l1,categoria=second,nome='Outro produto',preco='3.00')
        self.client.force_authenticate(None)
        response=self.client.get(f'/api/catalogo/lojas/{self.l1.pk}/produtos/',{'categoria':second.pk,'page':1,'page_size':1})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['count'],1)
        self.assertEqual(response.data['results'][0]['id'],product.pk)
        self.assertEqual(self.client.get(f'/api/catalogo/lojas/{self.l1.pk}/produtos/',{'categoria':self.cat2.pk}).status_code,404)
        for value in ('abc','',0,-1):self.assertEqual(self.client.get(f'/api/catalogo/lojas/{self.l1.pk}/produtos/',{'categoria':value}).status_code,400)

    def test_owner_creates_categories_and_assigns_only_own_products(self):
        self.client.force_authenticate(self.m1)
        response=self.client.post('/api/categorias/',{'nome':'Bebidas'},format='json')
        self.assertEqual(response.status_code,201)
        category=response.data['id']
        self.assertEqual(response.data['loja'],self.l1.pk)
        self.assertEqual(self.client.post('/api/categorias/',{'nome':'Bebidas'},format='json').status_code,400)
        self.assertEqual(self.client.post('/api/categorias/',{'nome':'Other shop','loja':self.l2.pk},format='json').status_code,400)
        self.assertEqual(self.client.patch(f'/api/produtos/{self.p1.pk}/',{'categoria':category},format='json').status_code,200)
        self.assertEqual(self.client.patch(f'/api/produtos/{self.p2.pk}/',{'categoria':category},format='json').status_code,404)
        self.assertEqual(self.client.patch(f'/api/categorias/{self.cat2.pk}/',{'nome':'Invaded'},format='json').status_code,404)
        self.client.force_authenticate(self.c1)
        self.assertEqual(self.client.post('/api/categorias/',{'nome':'Forbidden'},format='json').status_code,400)

    def test_owner_can_classify_only_own_store_and_invalid_type_is_rejected(self):
        kind=TipoLoja.objects.create(nome='Padaria')
        self.client.force_authenticate(self.m1)
        self.assertEqual(self.client.patch(f'/api/lojas/{self.l1.pk}/',{'tipo_loja':kind.pk},format='json').status_code,200)
        self.assertEqual(self.client.patch(f'/api/lojas/{self.l2.pk}/',{'tipo_loja':kind.pk},format='json').status_code,404)
        self.assertEqual(self.client.patch(f'/api/lojas/{self.l1.pk}/',{'tipo_loja':999999},format='json').status_code,400)
