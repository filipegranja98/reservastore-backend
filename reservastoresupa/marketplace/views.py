from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from reservastoresupa.lojas.models import Loja, Produto, Categoria, TipoLoja
from reservastoresupa.lojas.models.loja import lojas_publicas
from reservastoresupa.lojas.serializers import LojaPublicaSerializer, TipoLojaSerializer
from .pagination import OptionalPageNumberPagination
from .models import Perfil, Endereco, AreaEntrega, Carrinho, ItemCarrinho, Pedido
from .permissions import ClientePermission, LojistaPermission, papel_usuario
from .serializers import (StrictSerializer, CadastroSerializer, EnderecoSerializer, AreaEntregaSerializer,
    AdicionarItemSerializer, QuantidadeSerializer, CarrinhoSerializer, CheckoutSerializer,
    PreviaCheckoutSerializer, PreviaCheckoutOutputSerializer, PedidoSerializer, TransicaoSerializer, PagamentoSerializer, LojaAdministracaoSerializer)
from .services import adicionar_item, checkout, previa_checkout, mudar_status, mudar_pagamento, bloquear_cliente


class CadastroView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_cadastro"
    permission_classes = [AllowAny]
    authentication_classes = []
    def post(self, request):
        serializer = CadastroSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = serializer.save()
        except IntegrityError:
            raise ValidationError("Nome de usuário indisponível.")
        return Response({"id": user.pk, "username": user.username, "papel": user.perfil.papel}, status=201)


class ContaUpdateSerializer(StrictSerializer):
    first_name = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False)
    telefone = serializers.CharField(max_length=20, required=False)


class ContaView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        perfil = Perfil.objects.filter(user=request.user).first()
        return Response({"id": request.user.pk, "username": request.user.username, "first_name": request.user.first_name,
                         "email": request.user.email, "telefone": perfil.telefone if perfil else "", "papel": papel_usuario(request.user)})
    @transaction.atomic
    def patch(self, request):
        serializer = ContaUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attrs = serializer.validated_data
        for name in ("first_name", "email"):
            if name in attrs:
                setattr(request.user, name, attrs[name])
        request.user.save(update_fields=[name for name in ("first_name", "email") if name in attrs])
        if "telefone" in attrs:
            perfil, _ = Perfil.objects.get_or_create(user=request.user, defaults={"papel": "lojista" if Loja.objects.filter(dono=request.user).exists() else "cliente"})
            perfil.telefone = attrs["telefone"]
            perfil.save(update_fields=["telefone"])
        return self.get(request)


class SenhaSerializer(StrictSerializer):
    senha_atual = serializers.CharField(write_only=True, trim_whitespace=False)
    nova_senha = serializers.CharField(write_only=True, trim_whitespace=False)


class SenhaView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_password"

    @transaction.atomic
    def post(self, request):
        serializer = SenhaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        attrs = serializer.validated_data
        if not user.check_password(attrs["senha_atual"]):
            raise ValidationError({"senha_atual": "Senha atual incorreta."})
        if attrs["senha_atual"] == attrs["nova_senha"]:
            raise ValidationError({"nova_senha": "Escolha uma senha diferente."})
        try:
            validate_password(attrs["nova_senha"], user=user)
        except DjangoValidationError as error:
            raise ValidationError({"nova_senha": error.messages})
        user.set_password(attrs["nova_senha"])
        user.save(update_fields=["password"])
        BlacklistedToken.objects.bulk_create([BlacklistedToken(token=token) for token in OutstandingToken.objects.filter(user=user)], ignore_conflicts=True)
        return Response({"detail": "Senha alterada. Entre novamente em seus dispositivos."})


class EnderecoViewSet(viewsets.ModelViewSet):
    pagination_class = OptionalPageNumberPagination
    permission_classes = [IsAuthenticated, ClientePermission]
    serializer_class = EnderecoSerializer
    def get_queryset(self):
        return Endereco.objects.filter(cliente=self.request.user).order_by("pk")
    def perform_create(self, serializer):
        serializer.save(cliente=self.request.user)


class AreaEntregaViewSet(viewsets.ModelViewSet):
    pagination_class = OptionalPageNumberPagination
    permission_classes = [IsAuthenticated, LojistaPermission]
    serializer_class = AreaEntregaSerializer
    def get_queryset(self):
        return AreaEntrega.objects.filter(loja__dono=self.request.user).order_by("pk")
    def perform_create(self, serializer):
        loja = get_object_or_404(Loja, dono=self.request.user)
        try:
            with transaction.atomic():
                serializer.save(loja=loja)
        except IntegrityError:
            raise ValidationError("Área já cadastrada nesta loja.")
    def perform_update(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise ValidationError("Área já cadastrada nesta loja.")


class ProdutoPublicoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produto
        fields = ["id", "nome", "categoria", "preco", "imagem"]


class CategoriaPublicaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ["id", "nome"]


class AreaPublicaSerializer(serializers.ModelSerializer):
    class Meta:
        model = AreaEntrega
        fields = ["id", "condominio", "taxa", "prazo_estimado_minutos"]


def query_positive_id(request, field):
    raw = request.query_params.get(field)
    if raw is None:
        return None
    try:
        value = int(raw)
    except (ValueError, TypeError):
        raise ValidationError({field: "Informe um identificador inteiro positivo."})
    if value < 1:
        raise ValidationError({field: "Informe um identificador inteiro positivo."})
    return value


class TipoLojaViewSet(viewsets.ReadOnlyModelViewSet):
    pagination_class = OptionalPageNumberPagination
    permission_classes = [AllowAny]
    serializer_class = TipoLojaSerializer
    queryset = TipoLoja.objects.all().order_by("nome", "pk")


class CatalogoViewSet(viewsets.ReadOnlyModelViewSet):
    pagination_class = OptionalPageNumberPagination
    permission_classes = [AllowAny]
    serializer_class = LojaPublicaSerializer
    def get_queryset(self):
        queryset = lojas_publicas().select_related("tipo_loja").order_by("nome", "pk")
        kind = query_positive_id(self.request, "tipo_loja")
        return queryset.filter(tipo_loja_id=kind) if kind is not None else queryset
    def responder_lista(self, queryset, serializer_class):
        page = self.paginate_queryset(queryset)
        data = serializer_class(page if page is not None else queryset, many=True, context=self.get_serializer_context()).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    @action(detail=True, methods=["get"])
    def produtos(self, request, pk=None):
        loja = self.get_object()
        produtos = loja.produtos.filter(ativo=True, categoria__loja_id=F("loja_id")).order_by("nome", "pk")
        category = query_positive_id(request, "categoria")
        if category is not None:
            get_object_or_404(loja.categorias, pk=category)
            produtos = produtos.filter(categoria_id=category)
        return self.responder_lista(produtos, ProdutoPublicoSerializer)

    @action(detail=True, methods=["get"])
    def categorias(self, request, pk=None):
        return self.responder_lista(self.get_object().categorias.order_by("nome", "pk"), CategoriaPublicaSerializer)

    @action(detail=True, methods=["get"], url_path="areas-entrega")
    def areas_entrega(self, request, pk=None):
        return self.responder_lista(self.get_object().areas_entrega.filter(ativa=True).order_by("pk"), AreaPublicaSerializer)


class CarrinhosView(APIView):
    permission_classes = [IsAuthenticated, ClientePermission]
    def get(self, request):
        qs = Carrinho.objects.filter(cliente=request.user).order_by("loja_id")
        return Response(CarrinhoSerializer(qs, many=True).data)


class CarrinhoView(APIView):
    permission_classes = [IsAuthenticated, ClientePermission]
    def get(self, request, loja_id):
        carrinho = Carrinho.objects.filter(cliente=request.user, loja_id=loja_id).first()
        if carrinho is None:
            get_object_or_404(lojas_publicas(), pk=loja_id)
            return Response({"loja": loja_id, "itens": [], "subtotal": "0.00"})
        return Response(CarrinhoSerializer(carrinho).data)
    @transaction.atomic
    def delete(self, request, loja_id):
        bloquear_cliente(request.user)
        Carrinho.objects.filter(cliente=request.user, loja_id=loja_id).delete()
        return Response(status=204)


class ItensCarrinhoView(APIView):
    permission_classes = [IsAuthenticated, ClientePermission]
    def post(self, request, loja_id):
        serializer = AdicionarItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = adicionar_item(request.user, loja_id, serializer.validated_data["produto"], serializer.validated_data["quantidade"])
        return Response(CarrinhoSerializer(cart).data, status=201)


class ItemCarrinhoView(APIView):
    permission_classes = [IsAuthenticated, ClientePermission]
    @transaction.atomic
    def patch(self, request, loja_id, pk):
        bloquear_cliente(request.user)
        item = get_object_or_404(ItemCarrinho, pk=pk, carrinho__cliente=request.user, carrinho__loja_id=loja_id)
        serializer = QuantidadeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = adicionar_item(request.user, loja_id, item.produto_id, serializer.validated_data["quantidade"])
        return Response(CarrinhoSerializer(cart).data)
    @transaction.atomic
    def delete(self, request, loja_id, pk):
        bloquear_cliente(request.user)
        item = get_object_or_404(ItemCarrinho, pk=pk, carrinho__cliente=request.user, carrinho__loja_id=loja_id)
        item.delete()
        return Response(status=204)


class PedidoViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    pagination_class = OptionalPageNumberPagination
    permission_classes = [IsAuthenticated, ClientePermission]
    serializer_class = PedidoSerializer
    def get_queryset(self):
        return Pedido.objects.filter(cliente=self.request.user).select_related("loja").prefetch_related("itens", "eventos")
    def create(self, request, *args, **kwargs):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pedido, created = checkout(request.user, serializer.validated_data)
        return Response(self.get_serializer(pedido).data, status=201 if created else 200)
    @action(detail=False, methods=["post"])
    def previa(self, request):
        serializer = PreviaCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = previa_checkout(request.user, serializer.validated_data)
        return Response(PreviaCheckoutOutputSerializer(dados).data)

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        serializer = StrictSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(self.get_serializer(mudar_status(request.user, pk, "cancelado")).data)
    @action(detail=True, methods=["post"], url_path="confirmar-recebimento")
    def confirmar_recebimento(self, request, pk=None):
        serializer = StrictSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(self.get_serializer(mudar_status(request.user, pk, "entregue")).data)
    @action(detail=True, methods=["post"], url_path="informar-pagamento")
    def informar_pagamento(self, request, pk=None):
        serializer = StrictSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(self.get_serializer(mudar_pagamento(request.user, pk, "informado")).data)


class PedidosLojistaViewSet(viewsets.ReadOnlyModelViewSet):
    pagination_class = OptionalPageNumberPagination
    permission_classes = [IsAuthenticated, LojistaPermission]
    serializer_class = PedidoSerializer
    def get_queryset(self):
        qs = Pedido.objects.filter(loja__dono=self.request.user).select_related("loja").prefetch_related("itens", "eventos")
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        if self.request.query_params.get("fila") == "ativos":
            qs = qs.exclude(status__in=["entregue", "cancelado"])
        if self.request.query_params.get("ordem") == "antigos":
            qs = qs.order_by("criado_em", "pk")
        return qs
    @action(detail=True, methods=["post"])
    def transicao(self, request, pk=None):
        serializer = TransicaoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(self.get_serializer(mudar_status(request.user, pk, serializer.validated_data["status"], lojista=True)).data)
    @action(detail=True, methods=["post"])
    def pagamento(self, request, pk=None):
        serializer = PagamentoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(self.get_serializer(mudar_pagamento(request.user, pk, serializer.validated_data["status"], lojista=True)).data)


class LojasAdminViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    pagination_class = OptionalPageNumberPagination
    permission_classes = [IsAdminUser]
    serializer_class = LojaAdministracaoSerializer
    queryset = Loja.objects.order_by("pk")


class PedidosAdminViewSet(viewsets.ReadOnlyModelViewSet):
    pagination_class = OptionalPageNumberPagination
    permission_classes = [IsAdminUser]
    serializer_class = PedidoSerializer
    queryset = Pedido.objects.select_related("loja").prefetch_related("itens", "eventos").all()


class UsuarioAdminSerializer(serializers.ModelSerializer):
    papel = serializers.SerializerMethodField()
    class Meta:
        model = get_user_model()
        fields = ["id", "username", "first_name", "email", "is_active", "papel"]
    def get_papel(self, obj):
        return papel_usuario(obj)


class UsuariosAdminViewSet(viewsets.ReadOnlyModelViewSet):
    pagination_class = OptionalPageNumberPagination
    permission_classes = [IsAdminUser]
    serializer_class = UsuarioAdminSerializer
    queryset = get_user_model().objects.order_by("pk")
