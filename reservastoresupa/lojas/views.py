from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from .models import Produto, Loja, Categoria
from .serializers import LojaSerializer, ProdutoSerializer, CategoriaSerializer, LojaPublicaSerializer, serializers
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh_token")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()  # Envia para blacklist
                return Response({"message": "Logout realizado com sucesso."}, status=status.HTTP_205_RESET_CONTENT)
            return Response({"error": "Refresh token não fornecido."}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)







# View para login de usuários
from rest_framework_simplejwt.views import TokenObtainPairView

class LoginView(TokenObtainPairView):
    pass  # Já herda toda a lógica de autenticação do JWT


from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.response import Response
from rest_framework import status
from .serializers import CustomTokenObtainPairSerializer

class CustomLoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        try:
            # Chama a lógica padrão do TokenObtainPairView
            return super().post(request, *args, **kwargs)
        except serializers.ValidationError as e:
            # Se o erro for de validação (usuário ou senha inválidos), retorna a mensagem de erro personalizada
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Caso haja outro erro inesperado, retorna uma mensagem genérica
            return Response({"detail": "Erro inesperado no servidor."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)






# View para gerenciar produtos
class ProdutoViewSet(viewsets.ModelViewSet):
    serializer_class = ProdutoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        loja = Loja.objects.filter(dono=self.request.user).first()
        if loja:
            return Produto.objects.filter(loja=loja)
        return Produto.objects.none()  # Se o usuário não tem loja, não vê produtos

    def perform_create(self, serializer):
        loja = Loja.objects.filter(dono=self.request.user).first()
        if loja:
            serializer.save(loja=loja)
        else:
            raise ValidationError("Usuário não possui uma loja cadastrada.")

    def perform_update(self, serializer):
        produto = self.get_object()
        if produto.loja.dono != self.request.user:
            raise PermissionDenied("Você não tem permissão para editar este produto.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.loja.dono != self.request.user:
            raise PermissionDenied("Você não tem permissão para excluir este produto.")
        instance.delete()

# View para gerenciar categorias
class CategoriaViewSet(viewsets.ModelViewSet):
    serializer_class = CategoriaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        loja = Loja.objects.filter(dono=self.request.user).first()
        if loja:
            return Categoria.objects.filter(loja=loja)
        return Categoria.objects.none()  # Se o usuário não tem loja, não vê categorias

    def perform_create(self, serializer):
        loja = Loja.objects.filter(dono=self.request.user).first()
        if loja:
            if Categoria.objects.filter(loja=loja, nome=serializer.validated_data["nome"]).exists():
                raise ValidationError("Essa categoria já existe para sua loja.")
            serializer.save(loja=loja)
        else:
            raise ValidationError("Usuário não possui uma loja cadastrada.")

    def perform_update(self, serializer):
        categoria = self.get_object()
        if categoria.loja.dono != self.request.user:
            raise PermissionDenied("Você não tem permissão para editar esta categoria.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.loja.dono != self.request.user:
            raise PermissionDenied("Você não tem permissão para excluir esta categoria.")
        instance.delete()

# View para listar todas as lojas (para administradores ou usuários autenticados)
from rest_framework.permissions import AllowAny

class TodasLojasView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        lojas = Loja.objects.all()
        serializer = LojaPublicaSerializer(lojas, many=True)
        return Response(serializer.data)


class LojaViewSet(viewsets.ModelViewSet):
    serializer_class = LojaSerializer
    permission_classes = [IsAuthenticated]
    queryset = Loja.objects.all()

    def get_queryset(self):
        """Retorna apenas a loja do usuário logado."""
        return Loja.objects.filter(dono=self.request.user)

    @action(detail=False, methods=['GET'])
    def minha_loja(self, request):
        """Endpoint que retorna a loja vinculada ao usuário logado."""
        loja = get_object_or_404(Loja, dono=request.user)
        serializer = self.get_serializer(loja)
        return Response(serializer.data)

    @action(detail=False, methods=['GET'])
    def minha_loja_completa(self, request):
        """Endpoint que retorna todos os dados da loja do usuário logado (Loja, Produtos e Categorias)."""
        loja = get_object_or_404(Loja, dono=request.user)

        # Séries de serializadores
        loja_serializer = LojaSerializer(loja)
        produtos = Produto.objects.filter(loja=loja)
        categorias = Categoria.objects.filter(loja=loja)

        # Serializadores para produtos e categorias
        produtos_serializer = ProdutoSerializer(produtos, many=True)
        categorias_serializer = CategoriaSerializer(categorias, many=True)

        # Retorna todos os dados da loja, incluindo produtos e categorias
        response_data = {
            'loja': loja_serializer.data,
            'produtos': produtos_serializer.data,
            'categorias': categorias_serializer.data
        }

        return Response(response_data)