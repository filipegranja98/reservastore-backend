import io
from django.conf import settings
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase
from reservastoresupa.marketplace import tests as fixtures

class ProductImageTests(APITestCase):
    setUp=fixtures.MarketplaceTests.setUp

    def photo(self,large=False):
        stream=io.BytesIO()
        Image.new("RGB",(4,4),"green").save(stream,format="PNG")
        content=stream.getvalue()+(b"0"*(5*1024*1024) if large else b"")
        return SimpleUploadedFile("product.png",content,content_type="image/png")

    def test_owner_creates_edits_and_removes_product_image(self):
        self.client.force_authenticate(self.m1)
        with self.settings(STORAGES={**settings.STORAGES,"default":{"BACKEND":"django.core.files.storage.InMemoryStorage"}}):
            response=self.client.post("/api/produtos/",{"nome":"Photo product","categoria":self.cat1.pk,"preco":"15.50","imagem":self.photo()},format="multipart")
            self.assertEqual(response.status_code,201,response.data)
            self.assertIn("produtos/",response.data["imagem"])
            pk=response.data["id"]
            response=self.client.patch(f"/api/produtos/{pk}/",{"nome":"Edited","preco":"20.00","ativo":False,"imagem":self.photo()},format="multipart")
            self.assertEqual(response.status_code,200,response.data)
            self.assertFalse(response.data["ativo"])
            self.assertEqual(response.data["preco"],"20.00")
            response=self.client.patch(f"/api/produtos/{pk}/",{"imagem":None},format="json")
            self.assertEqual(response.status_code,200,response.data)
            self.assertIsNone(response.data["imagem"])

    def test_image_writes_remain_owner_scoped_and_reject_invalid_uploads(self):
        self.client.force_authenticate(self.m1)
        with self.settings(STORAGES={**settings.STORAGES,"default":{"BACKEND":"django.core.files.storage.InMemoryStorage"}}):
            self.assertEqual(self.client.patch(f"/api/produtos/{self.p2.pk}/",{"imagem":self.photo()},format="multipart").status_code,404)
            self.assertEqual(self.client.patch(f"/api/produtos/{self.p1.pk}/",{"imagem":self.photo(True)},format="multipart").status_code,400)
            self.assertEqual(self.client.patch(f"/api/produtos/{self.p1.pk}/",{"imagem":SimpleUploadedFile("fake.png",b"invalid",content_type="image/png")},format="multipart").status_code,400)
            self.assertEqual(self.client.post("/api/produtos/",{"nome":"Foreign","categoria":self.cat2.pk,"preco":"5.00","imagem":self.photo()},format="multipart").status_code,400)
