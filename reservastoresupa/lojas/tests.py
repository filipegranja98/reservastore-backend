from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from rest_framework.test import APITestCase
from .models import Loja, Categoria, Produto


class IsolationTests(APITestCase):
    def setUp(self):
        self.a = get_user_model().objects.create_user("a", password="secret-a")
        self.b = get_user_model().objects.create_user("b", password="secret-b")
        self.la = Loja.objects.create(dono=self.a, nome="A", whatsapp="111")
        self.lb = Loja.objects.create(dono=self.b, nome="B", whatsapp="222")
        self.ca = Categoria.objects.create(loja=self.la, nome="A")
        self.cb = Categoria.objects.create(loja=self.lb, nome="B")
        self.pa = Produto.objects.create(loja=self.la, categoria=self.ca, nome="A", preco="10")
        self.pb = Produto.objects.create(loja=self.lb, categoria=self.cb, nome="B", preco="20")
        self.client.force_authenticate(self.a)

    def test_lists_are_isolated(self):
        for endpoint, expected in [("lojas", self.la.pk), ("categorias", self.ca.pk), ("produtos", self.pa.pk)]:
            response = self.client.get(f"/api/{endpoint}/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual([x["id"] for x in response.data], [expected])

    def test_foreign_objects_cannot_be_read_changed_or_deleted(self):
        for endpoint, pk in [("lojas", self.lb.pk), ("categorias", self.cb.pk), ("produtos", self.pb.pk)]:
            url = f"/api/{endpoint}/{pk}/"
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.patch(url, {"nome": "invaded"}).status_code, 404)
            self.assertEqual(self.client.put(url, {"nome": "invaded"}).status_code, 404)
            self.assertEqual(self.client.delete(url).status_code, 404)

    def test_bindings_cannot_be_transferred(self):
        for endpoint, pk, binding, target in [("lojas", self.la.pk, "dono", self.b.pk),
                ("categorias", self.ca.pk, "loja", self.lb.pk), ("produtos", self.pa.pk, "loja", self.lb.pk)]:
            self.assertEqual(self.client.patch(f"/api/{endpoint}/{pk}/", {binding: target}).status_code, 400)
        self.pa.refresh_from_db()
        self.assertEqual(self.pa.loja_id, self.la.pk)

    def test_foreign_category_create_patch_and_put_rejected(self):
        payload = {"nome": "X", "preco": "5", "categoria": self.cb.pk}
        self.assertEqual(self.client.post("/api/produtos/", payload).status_code, 400)
        self.assertEqual(self.client.patch(f"/api/produtos/{self.pa.pk}/", {"categoria": self.cb.pk}).status_code, 400)
        self.assertEqual(self.client.put(f"/api/produtos/{self.pa.pk}/", payload).status_code, 400)

    def test_create_owned_product_and_category(self):
        response = self.client.post("/api/categorias/", {"nome": "new"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["loja"], self.la.pk)
        response = self.client.post("/api/produtos/", {"nome": "new", "preco": "0", "categoria": self.ca.pk})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["loja"], self.la.pk)

    def test_owned_catalog_can_be_updated_and_deleted(self):
        response = self.client.put(f"/api/produtos/{self.pa.pk}/", {"nome": "updated", "preco": "12.50", "categoria": self.ca.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["loja"], self.la.pk)
        self.assertEqual(self.client.patch(f"/api/categorias/{self.ca.pk}/", {"nome": "updated"}).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/produtos/{self.pa.pk}/").status_code, 204)
        self.assertEqual(self.client.delete(f"/api/categorias/{self.ca.pk}/").status_code, 204)
        self.assertTrue(Produto.objects.filter(pk=self.pb.pk).exists())

    def test_second_merchant_sees_only_own_catalog(self):
        self.client.force_authenticate(self.b)
        self.assertEqual([x["id"] for x in self.client.get("/api/produtos/").data], [self.pb.pk])
        self.assertEqual(self.client.get(f"/api/produtos/{self.pa.pk}/").status_code, 404)

    def test_negative_price_and_foreign_create_binding(self):
        for extra in [{"preco": "-1"}, {"loja": self.lb.pk}]:
            payload = {"nome": "new", "preco": "1", "categoria": self.ca.pk, **extra}
            self.assertEqual(self.client.post("/api/produtos/", payload).status_code, 400)
        self.assertEqual(self.client.post("/api/categorias/", {"nome": "x", "loja": self.lb.pk}).status_code, 400)

    def test_duplicate_category_update_rejected(self):
        other = Categoria.objects.create(loja=self.la, nome="other")
        self.assertEqual(self.client.patch(f"/api/categorias/{other.pk}/", {"nome": "A"}).status_code, 400)

    def test_store_creation_binds_authenticated_user_and_rejects_duplicate(self):
        c = get_user_model().objects.create_user("c")
        self.client.force_authenticate(c)
        self.assertEqual(self.client.post("/api/lojas/", {"nome": "C", "whatsapp": "333", "dono": self.a.pk}).status_code, 400)
        response = self.client.post("/api/lojas/", {"nome": "C", "whatsapp": "81988887777"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["dono"], c.pk)
        self.assertEqual(self.client.post("/api/lojas/", {"nome": "C2", "whatsapp": "333"}).status_code, 400)

    def test_no_store_cannot_create_catalog(self):
        self.client.force_authenticate(get_user_model().objects.create_user("c"))
        self.assertEqual(self.client.post("/api/categorias/", {"nome": "x"}).status_code, 400)

    def test_anonymous_management_requires_authentication(self):
        self.client.force_authenticate(None)
        for endpoint in ["lojas", "categorias", "produtos"]:
            self.assertEqual(self.client.get(f"/api/{endpoint}/").status_code, 401)

    def test_public_store_list_hides_owner_and_catalog(self):
        self.la.ativa = True
        self.la.assinatura_status = "ativa"
        self.la.save()
        self.client.force_authenticate(None)
        response = self.client.get("/api/lojas/todas_lojas")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data[0]), {"id", "nome", "tipo_loja", "tipo_loja_nome", "tipo_catalogo", "email_contato", "whatsapp", "logo", "aberta", "permite_entrega", "permite_retirada", "cor_primaria", "cor_secundaria", "meios_pagamento", "instrucoes_pagamento"})

    def test_legacy_cross_store_product_not_nested_in_other_store(self):
        Produto.objects.filter(pk=self.pb.pk).update(categoria=self.ca)
        response = self.client.get(f"/api/categorias/{self.ca.pk}/")
        self.assertEqual([p["id"] for p in response.data["produtos"]], [self.pa.pk])

    def test_model_rejects_cross_store_category(self):
        with self.assertRaises(ModelValidationError):
            Produto.objects.create(loja=self.la, categoria=self.cb, nome="X", preco="5")

    def test_complete_store_action(self):
        response = self.client.get("/api/lojas/minha_loja_completa")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["loja"]["id"], self.la.pk)
        self.assertEqual([p["id"] for p in response.data["produtos"]], [self.pa.pk])


class JWTTests(APITestCase):
    def setUp(self):
        self.a = get_user_model().objects.create_user("a", password="secret-a")
        self.b = get_user_model().objects.create_user("b", password="secret-b")

    def login(self, username="a", password="secret-a"):
        response = self.client.post("/api/token/", {"username": username, "password": password})
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_login_authenticated_access_refresh_rotation_logout(self):
        pair = self.login()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + pair["access"])
        self.assertEqual(self.client.get("/api/lojas/").status_code, 200)
        self.assertEqual(self.client.post("/api/token/verify/", {"token": pair["access"]}).status_code, 200)
        refreshed = self.client.post("/api/token/refresh/", {"refresh": pair["refresh"]})
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(self.client.post("/api/token/refresh/", {"refresh": pair["refresh"]}).status_code, 401)
        self.assertEqual(self.client.post("/api/token/logout/", {"refresh_token": refreshed.data["refresh"]}).status_code, 205)
        self.assertEqual(self.client.post("/api/token/refresh/", {"refresh": refreshed.data["refresh"]}).status_code, 401)

    def test_logout_cannot_revoke_another_users_refresh(self):
        a = self.login()
        b = self.login("b", "secret-b")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + a["access"])
        self.assertEqual(self.client.post("/api/token/logout/", {"refresh_token": b["refresh"]}).status_code, 400)
        self.assertEqual(self.client.post("/api/token/refresh/", {"refresh": b["refresh"]}).status_code, 200)

    def test_invalid_login_and_logout_tokens(self):
        self.assertEqual(self.client.post("/api/token/", {"username": "a", "password": "wrong"}).status_code, 401)
        self.assertEqual(self.client.post("/api/token/logout/", {}).status_code, 401)
        pair = self.login()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + pair["access"])
        for payload in [{}, {"refresh_token": "bad"}]:
            self.assertEqual(self.client.post("/api/token/logout/", payload).status_code, 400)


class StoreBrandingTests(APITestCase):
    setUp = IsolationTests.setUp
    def test_brand_colors_are_owned_validated_and_public(self):
        response = self.client.patch(f"/api/lojas/{self.la.pk}/", {"cor_primaria":"#243B7A","cor_secundaria":"#FFD166"})
        self.assertEqual(response.status_code, 200)
        self.lb.refresh_from_db()
        self.assertEqual(self.lb.cor_primaria, "#17624E")
        self.assertEqual(self.client.patch(f"/api/lojas/{self.lb.pk}/", {"cor_primaria":"#FFFFFF"}).status_code, 404)
        for field in ("cor_primaria", "cor_secundaria"):
            for value in ("", "red", "#FFF", "#GGGGGG", "url(example)"):
                self.assertEqual(self.client.patch(f"/api/lojas/{self.la.pk}/", {field:value}, format="json").status_code, 400)
        self.la.refresh_from_db()
        self.la.ativa=True
        self.la.assinatura_status="ativa"
        self.la.save()
        self.client.force_authenticate(None)
        data=self.client.get(f"/api/catalogo/lojas/{self.la.pk}/").data
        self.assertEqual(data["cor_primaria"],"#243B7A")
        self.assertEqual(data["cor_secundaria"],"#FFD166")
        self.assertNotIn("dono",data)

    def test_admin_form_contains_brand_fields_and_validates_colors(self):
        from django.forms import modelform_factory
        form_class=modelform_factory(Loja, fields=["logo","cor_primaria","cor_secundaria"])
        self.assertIn("logo",form_class.base_fields)
        form=form_class({"cor_primaria":"red","cor_secundaria":"#ABCDEF"})
        self.assertFalse(form.is_valid())
        self.assertIn("cor_primaria",form.errors)


class StoreContactTests(APITestCase):
    setUp = IsolationTests.setUp

    def test_store_admin_requires_name_owner_email_and_phone(self):
        from .forms import LojaAdminForm
        form=LojaAdminForm()
        self.assertEqual(form.fields["dono"].label,"Usuário do dono")
        self.assertEqual(form.fields["nome"].label,"Nome da loja")
        for field in ("nome","dono","email_contato","whatsapp"):
            self.assertTrue(form.fields[field].required)
        blank=LojaAdminForm(data={})
        self.assertFalse(blank.is_valid())
        for field in ("nome","dono","email_contato","whatsapp"):
            self.assertIn(field,blank.errors)

    def test_store_admin_requires_phone_with_ddd(self):
        from .forms import LojaAdminForm
        invalid=LojaAdminForm(data={"whatsapp":"111"})
        invalid.is_valid()
        self.assertIn("whatsapp",invalid.errors)
        valid=LojaAdminForm(data={"whatsapp":"(85) 99999-0000"})
        valid.is_valid()
        self.assertNotIn("whatsapp",valid.errors)

    def test_contact_email_validated_and_exposed_without_owner_account_email(self):
        self.a.email="private-owner@example.test"
        self.a.save(update_fields=["email"])
        url=f"/api/lojas/{self.la.pk}/"
        self.assertEqual(self.client.patch(url,{"email_contato":"invalid"},format="json").status_code,400)
        self.assertEqual(self.client.patch(url,{"email_contato":"store@example.test","whatsapp":"85999990000"},format="json").status_code,200)
        self.la.refresh_from_db()
        self.la.ativa=True
        self.la.assinatura_status="ativa"
        self.la.save()
        self.client.force_authenticate(None)
        data=self.client.get(f"/api/catalogo/lojas/{self.la.pk}/").data
        self.assertEqual(data["email_contato"],"store@example.test")
        self.assertEqual(data["whatsapp"],"85999990000")
        self.assertNotIn("private-owner@example.test",str(data))
