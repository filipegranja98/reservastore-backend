from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from reservastoresupa.marketplace.pagination import OptionalPageNumberPagination
from .models import Loja, Categoria, Produto
from .models.loja import lojas_publicas
from .serializers import LojaSerializer, CategoriaSerializer, ProdutoSerializer, LojaPublicaSerializer


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        value = request.data.get("refresh_token")
        if not value:
            raise ValidationError({"refresh_token": "Informe o refresh token."})
        try:
            token = RefreshToken(value)
            if str(token["user_id"]) != str(request.user.pk):
                raise ValidationError({"refresh_token": "O token não pertence ao usuário autenticado."})
            token.blacklist()
        except TokenError:
            raise ValidationError({"refresh_token": "Token inválido ou expirado."})
        return Response(status=status.HTTP_205_RESET_CONTENT)


class OwnedViewSet(viewsets.ModelViewSet):
    pagination_class = OptionalPageNumberPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.serializer_class.Meta.model.objects.filter(loja__dono=self.request.user).order_by("pk")

    def perform_create(self, serializer):
        loja = get_object_or_404(Loja, dono=self.request.user)
        serializer.save(loja=loja)


class ProdutoViewSet(OwnedViewSet):
    serializer_class = ProdutoSerializer


class CategoriaViewSet(OwnedViewSet):
    serializer_class = CategoriaSerializer


class TodasLojasView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(LojaPublicaSerializer(lojas_publicas(), many=True, context={"request": request}).data)


class LojaViewSet(viewsets.ModelViewSet):
    pagination_class = OptionalPageNumberPagination
    serializer_class = LojaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Loja.objects.filter(dono=self.request.user).order_by("pk")

    def perform_create(self, serializer):
        from reservastoresupa.marketplace.models import Perfil
        if self.request.user.is_staff or Perfil.objects.filter(user=self.request.user, papel="cliente").exists():
            raise PermissionDenied("Cadastre uma conta de lojista para criar sua loja.")
        if Loja.objects.filter(dono=self.request.user).exists():
            raise ValidationError("Usuário já possui uma loja.")
        try:
            with transaction.atomic():
                serializer.save(dono=self.request.user)
                Perfil.objects.get_or_create(user=self.request.user, defaults={"papel": "lojista"})
        except IntegrityError:
            raise ValidationError("Usuário já possui uma loja.")

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError("Loja com pedidos não pode ser excluída. Solicite sua desativação ao administrador.")

    @action(detail=False, methods=["get"])
    def minha_loja(self, request):
        return Response(self.get_serializer(get_object_or_404(self.get_queryset())).data)

    @action(detail=False, methods=["get"])
    def minha_loja_completa(self, request):
        loja = get_object_or_404(self.get_queryset())
        return Response({"loja": self.get_serializer(loja).data,
            "produtos": ProdutoSerializer(loja.produtos.all(), many=True, context=self.get_serializer_context()).data,
            "categorias": CategoriaSerializer(loja.categorias.all(), many=True, context=self.get_serializer_context()).data})
