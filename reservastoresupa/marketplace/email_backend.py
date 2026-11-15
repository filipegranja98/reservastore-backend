"""Resend delivery for Reserva Store; credentials belong only to this project."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self,email_messages):
        sent=0
        for message in email_messages or []:
            if not message.recipients():
                continue
            try:
                if not settings.RESEND_API_KEY:
                    raise ValueError("Configuração ausente.")
                payload={"from":message.from_email,"to":message.to,"subject":message.subject,"text":message.body}
                if message.cc: payload["cc"]=message.cc
                if message.bcc: payload["bcc"]=message.bcc
                if message.reply_to: payload["reply_to"]=message.reply_to
                request=Request("https://api.resend.com/emails",data=json.dumps(payload).encode(),method="POST",headers={"Authorization":f"Bearer {settings.RESEND_API_KEY}","Content-Type":"application/json","User-Agent":"ReservaStore/1.0"})
                with urlopen(request,timeout=settings.EMAIL_TIMEOUT) as response:
                    result=json.loads(response.read())
                    if not result.get("id"): raise ValueError("Envio não confirmado.")
                sent+=1
            except (HTTPError,URLError,OSError,ValueError):
                if not self.fail_silently:
                    raise RuntimeError("Não foi possível enviar o e-mail do Reserva Store.") from None
        return sent
