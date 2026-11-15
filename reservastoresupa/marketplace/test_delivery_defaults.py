from django.test import TestCase
from django.contrib.auth import get_user_model
from reservastoresupa.lojas.models import Loja
from .models import AreaEntrega
from .condominiums import CONDOMINIOS_RESERVA
from .delivery_defaults import ensure_reserva_areas

class DeliveryDefaultsTests(TestCase):
    def test_new_store_receives_all_condominiums_without_enabling_delivery(self):
        owner=get_user_model().objects.create_user(username="new-coverage")
        shop=Loja.objects.create(dono=owner,nome="Coverage",permite_entrega=False)
        areas=AreaEntrega.objects.filter(loja=shop)
        self.assertEqual(set(areas.values_list("condominio",flat=True)),set(CONDOMINIOS_RESERVA))
        self.assertTrue(all(area.ativa and area.taxa==0 for area in areas))
        shop.refresh_from_db()
        self.assertFalse(shop.permite_entrega)
        self.assertFalse(shop.permite_retirada)

    def test_coverage_keeps_existing_fees_and_is_idempotent(self):
        owner=get_user_model().objects.create_user(username="existing-coverage")
        shop=Loja.objects.create(dono=owner,nome="Coverage")
        area=shop.areas_entrega.get(condominio="Condomínio Ébano")
        area.taxa="4.50"; area.ativa=False; area.save()
        ensure_reserva_areas(shop); ensure_reserva_areas(shop)
        area.refresh_from_db()
        self.assertTrue(area.ativa)
        self.assertEqual(str(area.taxa),"4.50")
        self.assertEqual(shop.areas_entrega.count(),14)
