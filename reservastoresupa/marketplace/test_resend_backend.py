import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
from django.core.mail import EmailMessage
from django.test import SimpleTestCase,override_settings
from .email_backend import ResendEmailBackend

@override_settings(RESEND_API_KEY="synthetic-resend-key",EMAIL_TIMEOUT=10)
class ResendBackendTests(SimpleTestCase):
    def test_payload_keeps_reserva_identity_and_uses_https(self):
        message=EmailMessage("Recuperar conta — Reserva Store","Synthetic body","Reserva Store <sender@example.test>",["customer@example.test"])
        with patch("reservastoresupa.marketplace.email_backend.urlopen") as send:
            send.return_value.__enter__.return_value.read.return_value=b'{"id":"synthetic"}'
            self.assertEqual(ResendEmailBackend().send_messages([message]),1)
            request=send.call_args.args[0]
            self.assertEqual(request.full_url,"https://api.resend.com/emails")
            payload=json.loads(request.data)
            self.assertEqual(payload["from"],"Reserva Store <sender@example.test>")
            self.assertIn("Reserva Store",payload["subject"])
            self.assertEqual(request.headers["Authorization"],"Bearer synthetic-resend-key")

    def test_errors_do_not_expose_key_recipient_or_provider_response(self):
        message=EmailMessage("Test","Synthetic","sender@example.test",["customer@example.test"])
        with patch("reservastoresupa.marketplace.email_backend.urlopen",side_effect=HTTPError("https://api.resend.com/emails",403,"private-provider-response",{},BytesIO(b"private"))):
            with self.assertRaises(RuntimeError) as error:
                ResendEmailBackend().send_messages([message])
            self.assertNotIn("synthetic-resend-key",str(error.exception))
            self.assertNotIn("customer@example.test",str(error.exception))
            self.assertEqual(ResendEmailBackend(fail_silently=True).send_messages([message]),0)
