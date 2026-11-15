from hmac import compare_digest
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.serializers import TokenRefreshSerializer, TokenVerifySerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken
from rest_framework_simplejwt.utils import get_md5_hash_password
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView


def validar_conta_token(token):
    user = get_user_model().objects.filter(pk=token.get(api_settings.USER_ID_CLAIM)).first()
    if user is None or not user.is_active:
        raise AuthenticationFailed("Token inválido para esta conta.")
    claim = token.get(api_settings.REVOKE_TOKEN_CLAIM, "")
    if not isinstance(claim, str) or not compare_digest(claim, get_md5_hash_password(user.password)):
        raise AuthenticationFailed("Token revogado. Entre novamente.")
    return user


class LoginView(TokenObtainPairView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_login"


class SecureTokenRefreshSerializer(TokenRefreshSerializer):
    @transaction.atomic
    def validate(self, attrs):
        token = RefreshToken(attrs["refresh"])
        validar_conta_token(token)
        token.outstand()
        OutstandingToken.objects.select_for_update().get(jti=token[api_settings.JTI_CLAIM])
        # Recheck the blacklist after acquiring the lock, so a concurrent refresh cannot reuse it.
        validar_conta_token(RefreshToken(attrs["refresh"]))
        return super().validate(attrs)


class RefreshView(TokenRefreshView):
    serializer_class = SecureTokenRefreshSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_refresh"


class SecureTokenVerifySerializer(TokenVerifySerializer):
    def validate(self, attrs):
        validar_conta_token(UntypedToken(attrs["token"]))
        return super().validate(attrs)


class VerifyView(TokenVerifyView):
    serializer_class = SecureTokenVerifySerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_refresh"
