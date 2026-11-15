import re
from datetime import datetime,timedelta
from unittest.mock import patch
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from . import tests as fixtures

@override_settings(ACCOUNT_RECOVERY_ENABLED=True,ACCOUNT_RECOVERY_TEST_MODE=False,EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RecoveryTests(APITestCase):
    def setUp(self):
        fixtures.MarketplaceTests.setUp(self)
        cache.clear()
        self.c1.email="customer@example.test";self.c1.save(update_fields=["email"])
        self.client.force_authenticate(None)

    def request_code(self):
        return self.client.post("/api/auth/recuperar-senha/",{"email":self.c1.email},format="json")

    def code(self):
        return re.search(r"[A-Za-z0-9_-]+\.[a-z0-9]+-[a-f0-9]+",mail.outbox[-1].body).group()

    def reset(self,code):
        return self.client.post("/api/auth/redefinir-senha/",{"codigo":code,"nova_senha":"Synthetic-reset-Strong!84"},format="json")

    def test_generic_responses_do_not_disclose_account_and_only_matching_email_receives_code(self):
        response=self.request_code()
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(mail.outbox),1)
        unknown=self.client.post("/api/auth/recuperar-senha/",{"email":"missing@example.test"},format="json")
        wrong=self.client.post("/api/auth/recuperar-senha/",{"email":"wrong@example.test"},format="json")
        self.assertEqual(response.data,unknown.data)
        self.assertEqual(response.data,wrong.data)
        self.assertEqual(len(mail.outbox),1)
        self.assertNotIn("codigo",response.data)
        self.assertIn("15 minutos",mail.outbox[0].body)

    def test_reset_is_single_use_and_revokes_existing_tokens(self):
        login=self.client.post("/api/token/",{"username":self.c1.username,"password":"customer-pass"},format="json")
        self.assertEqual(login.status_code,200)
        self.request_code();code=self.code()
        response=self.reset(code)
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(self.reset(code).status_code,400)
        self.assertEqual(self.client.post("/api/token/refresh/",{"refresh":login.data["refresh"]},format="json").status_code,401)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer "+login.data["access"])
        self.assertEqual(self.client.get("/api/conta/").status_code,401)
        self.client.credentials()
        self.assertEqual(self.client.post("/api/token/",{"username":self.c1.username,"password":"Synthetic-reset-Strong!84"},format="json").status_code,200)

    def test_expired_tampered_and_weak_password_requests_fail(self):
        with patch.object(default_token_generator,"_now",return_value=datetime.now()-timedelta(minutes=16)):
            self.request_code()
        self.assertEqual(self.reset(self.code()).status_code,400)
        self.assertEqual(self.reset("invalid.invalid").status_code,400)
        self.request_code();code=self.code()
        weak=self.client.post("/api/auth/redefinir-senha/",{"codigo":code,"nova_senha":"123"},format="json")
        self.assertEqual(weak.status_code,400)
        self.assertEqual(self.reset(code+"invalid").status_code,400)

    def test_merchant_accounts_are_not_recovered_through_customer_endpoint(self):
        self.m1.email="merchant@example.test";self.m1.save(update_fields=["email"])
        response=self.client.post("/api/auth/recuperar-senha/",{"email":self.m1.email},format="json")
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(mail.outbox),0)

    @override_settings(ACCOUNT_RECOVERY_ENABLED=False)
    def test_unconfigured_production_does_not_claim_email_is_enabled(self):
        self.assertEqual(self.request_code().status_code,503)

    def test_email_only_is_case_insensitive_and_handles_shared_email(self):
        self.c2.email=self.c1.email.upper();self.c2.save(update_fields=["email"])
        response=self.client.post("/api/auth/recuperar-senha/",{"email":self.c1.email.upper()},format="json")
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(mail.outbox),2)
        self.assertTrue(any(f"Conta: {self.c1.username}" in message.body for message in mail.outbox))
        self.assertTrue(any(f"Conta: {self.c2.username}" in message.body for message in mail.outbox))
