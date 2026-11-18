from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from .models import Perfil, Endereco, AreaEntrega, Carrinho, ItemCarrinho, Pedido, ItemPedido, EventoPedido, normalizar_condominio
from reservastoresupa.lojas.models import Loja

MEIOS_PAGAMENTO = ["pix", "dinheiro", "credito", "debito"]


class StrictMixin:
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            return super().to_internal_value(data)
        invalid = set(data) - {name for name, field in self.fields.items() if not field.read_only}
        if invalid:
            raise serializers.ValidationError({name: "Campo não permitido nesta operação." for name in sorted(invalid)})
        return super().to_internal_value(data)


class StrictSerializer(StrictMixin, serializers.Serializer):
    pass


class CadastroSerializer(StrictSerializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    telefone = serializers.CharField(max_length=20)
    papel = serializers.ChoiceField(choices=["cliente", "lojista"], default="cliente")

    def validate_username(self, value):
        field = get_user_model()._meta.get_field("username")
        try:
            field.run_validators(value)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages)
        if get_user_model().objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Nome de usuário indisponível.")
        return value

    def validate(self, attrs):
        user = get_user_model()(username=attrs["username"], email=attrs["email"], first_name=attrs["first_name"])
        try:
            validate_password(attrs["password"], user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": error.messages})
        return attrs

    @transaction.atomic
    def create(self, attrs):
        papel = attrs.pop("papel")
        telefone = attrs.pop("telefone")
        user = get_user_model().objects.create_user(**attrs)
        Perfil.objects.create(user=user, papel=papel, telefone=telefone)
        return user


class EnderecoSerializer(StrictMixin, serializers.ModelSerializer):
    class Meta:
        model = Endereco
        fields = ["id", "condominio", "bloco", "apartamento", "destinatario", "telefone", "complemento"]
        read_only_fields = ["id"]


class AreaEntregaSerializer(StrictMixin, serializers.ModelSerializer):
    class Meta:
        model = AreaEntrega
        fields = ["id", "loja", "condominio", "taxa", "ativa", "prazo_estimado_minutos"]
        read_only_fields = ["id", "loja"]
        extra_kwargs = {"taxa": {"min_value": 0}}

    def validate(self, attrs):
        loja = Loja.objects.filter(dono=self.context["request"].user).first()
        if loja is None:
            raise serializers.ValidationError("Cadastre sua loja primeiro.")
        nome = normalizar_condominio(attrs.get("condominio", getattr(self.instance, "condominio", "")))
        if not nome:
            raise serializers.ValidationError({"condominio": "Informe o condomínio."})
        qs = AreaEntrega.objects.filter(loja=loja, condominio_normalizado=nome)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"condominio": "Área já cadastrada nesta loja."})
        return attrs


class AdicionarItemSerializer(StrictSerializer):
    produto = serializers.IntegerField(min_value=1)
    quantidade = serializers.IntegerField(min_value=1, max_value=99)


class QuantidadeSerializer(StrictSerializer):
    quantidade = serializers.IntegerField(min_value=1, max_value=99)


class ItemCarrinhoSerializer(serializers.ModelSerializer):
    nome = serializers.CharField(source="produto.nome", read_only=True)
    preco_unitario = serializers.DecimalField(source="produto.preco_atual", max_digits=10, decimal_places=2, read_only=True)
    total = serializers.SerializerMethodField()
    class Meta:
        model = ItemCarrinho
        fields = ["id", "produto", "nome", "preco_unitario", "quantidade", "total"]
    def get_total(self, obj):
        return str(obj.produto.preco_atual * obj.quantidade)


class CarrinhoSerializer(serializers.ModelSerializer):
    itens = ItemCarrinhoSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()
    class Meta:
        model = Carrinho
        fields = ["id", "loja", "itens", "subtotal"]
    def get_subtotal(self, obj):
        return format(sum((item.produto.preco_atual * item.quantidade for item in obj.itens.select_related("produto")), start=0), ".2f")


class CheckoutSerializer(StrictSerializer):
    chave_checkout = serializers.UUIDField(required=False)
    loja = serializers.IntegerField(min_value=1)
    modalidade = serializers.ChoiceField(choices=["entrega", "retirada"], default="entrega")
    endereco = serializers.IntegerField(min_value=1, required=False)
    area_entrega = serializers.IntegerField(min_value=1, required=False)
    meio_pagamento = serializers.ChoiceField(choices=MEIOS_PAGAMENTO)
    precisa_troco = serializers.BooleanField(default=False)
    troco_para = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True, default=None)
    observacoes = serializers.CharField(max_length=1000, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["meio_pagamento"] != "dinheiro" and (attrs["precisa_troco"] or attrs["troco_para"] is not None):
            raise serializers.ValidationError("Troco é permitido somente para pagamento em dinheiro.")
        if attrs["precisa_troco"] and attrs["troco_para"] is None:
            raise serializers.ValidationError({"troco_para":"Informe para qual valor precisa de troco."})
        if not attrs["precisa_troco"] and attrs["troco_para"] is not None:
            raise serializers.ValidationError({"troco_para":"Selecione que precisa de troco ou remova o valor."})
        if attrs["modalidade"] == "entrega" and (not attrs.get("endereco") or not attrs.get("area_entrega")):
            raise serializers.ValidationError("Selecione endereço e área para entrega.")
        if attrs["modalidade"] == "retirada" and ("endereco" in attrs or "area_entrega" in attrs):
            raise serializers.ValidationError("Retirada não utiliza endereço nem área de entrega.")
        return attrs


class PreviaCheckoutSerializer(CheckoutSerializer):
    # A preview validates the intended purchase but never consumes an idempotency key.
    chave_checkout = None


class ItemPreviaSerializer(serializers.Serializer):
    produto = serializers.IntegerField()
    nome = serializers.CharField()
    preco_unitario = serializers.DecimalField(max_digits=10, decimal_places=2)
    quantidade = serializers.IntegerField()
    total = serializers.DecimalField(max_digits=14, decimal_places=2)


class PreviaCheckoutOutputSerializer(serializers.Serializer):
    loja = serializers.IntegerField()
    loja_nome = serializers.CharField()
    modalidade = serializers.CharField()
    area_entrega = serializers.IntegerField(allow_null=True)
    endereco = EnderecoSerializer(allow_null=True)
    meio_pagamento = serializers.CharField()
    precisa_troco = serializers.BooleanField()
    troco_para = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    valor_troco = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True)
    instrucoes_pagamento = serializers.CharField(allow_blank=True)
    itens = ItemPreviaSerializer(many=True)
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=2)
    taxa_entrega = serializers.DecimalField(max_digits=10, decimal_places=2)
    total = serializers.DecimalField(max_digits=14, decimal_places=2)
    prazo_estimado_minutos = serializers.IntegerField(allow_null=True)


class ItemPedidoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemPedido
        fields = ["id", "produto", "nome", "preco_unitario", "quantidade", "total"]


class EventoPedidoSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventoPedido
        fields = ["id", "autor", "tipo", "anterior", "novo", "criado_em"]


class PedidoSerializer(serializers.ModelSerializer):
    valor_troco = serializers.SerializerMethodField()

    def get_valor_troco(self, obj):
        return format(obj.troco_para - obj.total, ".2f") if obj.precisa_troco and obj.troco_para is not None else None

    itens = ItemPedidoSerializer(many=True, read_only=True)
    eventos = EventoPedidoSerializer(many=True, read_only=True)
    loja_nome = serializers.CharField(source="loja.nome", read_only=True)
    class Meta:
        model = Pedido
        fields = ["id", "codigo", "chave_checkout", "loja", "loja_nome", "modalidade", "status", "pagamento_status", "meio_pagamento", "precisa_troco", "troco_para", "valor_troco",
                  "instrucoes_pagamento", "endereco", "observacoes", "subtotal", "taxa_entrega", "prazo_estimado_minutos", "total", "criado_em", "atualizado_em", "itens", "eventos"]


class TransicaoSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=[v for v, _ in Pedido.STATUS])


class PagamentoSerializer(StrictSerializer):
    status = serializers.ChoiceField(choices=["confirmado", "estornado"])


class LojaAdministracaoSerializer(StrictMixin, serializers.ModelSerializer):
    class Meta:
        model = Loja
        fields = ["id", "nome", "dono", "ativa", "assinatura_status", "assinatura_valida_ate", "mensalidade"]
        read_only_fields = ["id", "nome", "dono"]
        extra_kwargs = {"mensalidade": {"min_value": 0}}
