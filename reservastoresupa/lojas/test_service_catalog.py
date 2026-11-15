from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import Loja, TipoLoja
from .serializers import LojaPublicaSerializer, LojaSerializer

class ServiceCatalogTests(TestCase):
    def test_catalog_mode_is_derived_from_store_type(self):
        user = get_user_model().objects.create_user(username="service-owner")
        kind = TipoLoja.objects.create(nome="Limpeza", modo_catalogo="servicos")
        shop = Loja.objects.create(dono=user, nome="Service", tipo_loja=kind)
        self.assertEqual(LojaPublicaSerializer(shop).data["tipo_catalogo"], "servicos")
        self.assertEqual(LojaSerializer(shop).data["tipo_catalogo"], "servicos")
        shop.tipo_loja = None
        self.assertEqual(LojaPublicaSerializer(shop).data["tipo_catalogo"], "produtos")
