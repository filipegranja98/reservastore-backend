from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from .models import Loja, TipoLoja
from .serializers import LojaPublicaSerializer


class StoreProfileTests(APITestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username="owner")
        self.other = get_user_model().objects.create_user(username="other")
        self.shop = Loja.objects.create(dono=self.owner, nome="Shop", whatsapp="81999990000")
        self.client.force_authenticate(self.owner)
        self.url = f"/api/lojas/{self.shop.pk}/"

    def test_owner_selects_service_profile_independent_of_category(self):
        response = self.client.patch(self.url, {"tipo_catalogo": "servicos"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.catalogo_efetivo, "servicos")
        self.assertEqual(LojaPublicaSerializer(self.shop).data["tipo_catalogo"], "servicos")
        self.assertEqual(self.client.patch(self.url, {"tipo_catalogo": "produtos"}, format="json").data["tipo_catalogo"], "produtos")

    def test_owner_changes_public_contact(self):
        response = self.client.patch(self.url, {"whatsapp": "(81) 98888-7777"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.shop.refresh_from_db()
        self.assertEqual(LojaPublicaSerializer(self.shop).data["whatsapp"], "(81) 98888-7777")

    def test_invalid_phone_and_profile_are_rejected(self):
        for fields in [{"whatsapp": "123"}, {"whatsapp": "abcdefghij"}, {"tipo_catalogo": "admin"}]:
            self.assertEqual(self.client.patch(self.url, fields, format="json").status_code, 400)

    def test_other_owner_cannot_change_profile_or_contact(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.patch(self.url, {"tipo_catalogo": "servicos", "whatsapp": "81988887777"}, format="json").status_code, 404)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.whatsapp, "81999990000")
        self.assertEqual(self.shop.catalogo_efetivo, "produtos")
