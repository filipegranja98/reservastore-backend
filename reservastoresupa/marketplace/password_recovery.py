import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from .serializers import StrictSerializer

GENERIC="Se o e-mail corresponder a uma conta de cliente, você receberá as instruções de recuperação."

class RecoveryRequestSerializer(StrictSerializer):
    email=serializers.EmailField()

class RecoveryConfirmSerializer(StrictSerializer):
    codigo=serializers.CharField(max_length=250,trim_whitespace=True)
    nova_senha=serializers.CharField(max_length=128,trim_whitespace=False,write_only=True)

class RecoveryBase(APIView):
    permission_classes=[AllowAny]
    authentication_classes=[]
    throttle_classes=[ScopedRateThrottle]

class PasswordRecoveryRequest(RecoveryBase):
    throttle_scope="password_reset_request"
    def post(self,request):
        if not settings.ACCOUNT_RECOVERY_ENABLED:
            return Response({"detail":"Recuperação de senha indisponível. Entre em contato com o responsável pelo Reserva Store."},status=503)
        serializer=RecoveryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data=serializer.validated_data
        users=get_user_model().objects.filter(email__iexact=data["email"],is_active=True,is_staff=False,is_superuser=False,perfil__papel="cliente")
        for user in users:
            if not user.has_usable_password():
                continue
            uid=urlsafe_base64_encode(force_bytes(user.pk))
            code=f"{uid}.{default_token_generator.make_token(user)}"
            body=(f"Conta: {user.username}\n\n"
                  "Recebemos uma solicitação para trocar sua senha do Reserva Store.\n\n"
                  "No app, abra Entrar → Esqueci minha senha → Já tenho um código.\n"
                  f"Cole este código no campo de recuperação:\n{code}\n\n"
                  "O código expira em 15 minutos e só pode ser usado uma vez.\n"
                  "Se você não solicitou a troca, ignore esta mensagem. Não compartilhe este código.")
            try:
                send_mail("Recuperar sua conta — Reserva Store",body,settings.DEFAULT_FROM_EMAIL,[user.email],fail_silently=False)
            except Exception:
                # Never log recipient, reset code, password, or mail-provider response.
                logging.getLogger(__name__).error("Falha no envio de recuperação de senha.")
        return Response({"detail":GENERIC,"modo_teste":settings.ACCOUNT_RECOVERY_TEST_MODE})

class PasswordRecoveryConfirm(RecoveryBase):
    throttle_scope="password_reset_confirm"
    @transaction.atomic
    def post(self,request):
        if not settings.ACCOUNT_RECOVERY_ENABLED:
            return Response({"detail":"Recuperação de senha indisponível."},status=503)
        serializer=RecoveryConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data=serializer.validated_data
        user=None
        try:
            uid,token=data["codigo"].split(".",1)
            pk=urlsafe_base64_decode(uid).decode()
            if not pk.isdigit(): raise ValueError()
            user=get_user_model().objects.select_for_update().filter(pk=pk,is_active=True,is_staff=False,is_superuser=False,perfil__papel="cliente").first()
        except (ValueError,UnicodeDecodeError,OverflowError):
            token=""
        if user is None or not user.has_usable_password() or not default_token_generator.check_token(user,token):
            raise serializers.ValidationError({"codigo":"Código inválido ou expirado. Solicite uma nova recuperação."})
        try:
            validate_password(data["nova_senha"],user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"nova_senha":error.messages})
        user.set_password(data["nova_senha"])
        user.save(update_fields=["password"])
        BlacklistedToken.objects.bulk_create([BlacklistedToken(token=item) for item in OutstandingToken.objects.filter(user=user)],ignore_conflicts=True)
        return Response({"detail":"Senha alterada. Entre novamente com sua nova senha."})
