from rest_framework import serializers
from .models import Loja, Categoria, Produto, TipoLoja


class BoundSerializer(serializers.ModelSerializer):
    """Reject client-supplied ownership changes instead of silently accepting them."""
    binding = "loja"

    def validate(self, attrs):
        user = self.context["request"].user
        expected = user.pk if self.binding == "dono" else Loja.objects.filter(dono=user).values_list("pk", flat=True).first()
        supplied = self.initial_data.get(self.binding)
        if self.binding in self.initial_data and str(supplied) != str(expected):
            raise serializers.ValidationError({self.binding: "Este vínculo não pode ser alterado."})
        if self.binding == "loja" and expected is None:
            raise serializers.ValidationError("Usuário não possui uma loja cadastrada.")
        return attrs


class ProdutoSerializer(BoundSerializer):
    class Meta:
        model = Produto
        fields = ["id", "loja", "categoria", "nome", "preco", "imagem", "ativo"]
        read_only_fields = ["loja"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        self.fields["categoria"].queryset = Categoria.objects.filter(loja__dono=request.user) if request and request.user.is_authenticated else Categoria.objects.none()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        categoria = attrs.get("categoria", getattr(self.instance, "categoria", None))
        loja = Loja.objects.filter(dono=self.context["request"].user).first()
        if categoria is not None and categoria.loja_id != getattr(loja, "pk", None):
            raise serializers.ValidationError({"categoria": "A categoria deve pertencer à mesma loja."})
        return attrs

    def validate_imagem(self, value):
        if value is None:
            return value
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("A imagem deve ter no máximo 5 MB.")
        if getattr(getattr(value, "image", None), "format", None) not in {"JPEG", "PNG", "WEBP"}:
            raise serializers.ValidationError("Use uma imagem JPG, PNG ou WebP.")
        return value

    def validate_preco(self, value):
        if value < 0:
            raise serializers.ValidationError("O preço não pode ser negativo.")
        return value


class CategoriaSerializer(BoundSerializer):
    produtos = serializers.SerializerMethodField()
    class Meta:
        model = Categoria
        fields = ["id", "nome", "loja", "produtos"]
        read_only_fields = ["loja"]

    def get_produtos(self, obj):
        # Avoid leaking legacy products with inconsistent cross-store links.
        return ProdutoSerializer(obj.produtos.filter(loja_id=obj.loja_id), many=True, context=self.context).data

    def validate(self, attrs):
        attrs = super().validate(attrs)
        qs = Categoria.objects.filter(loja__dono=self.context["request"].user,
                                      nome=attrs.get("nome", getattr(self.instance, "nome", "")))
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"nome": "Essa categoria já existe para sua loja."})
        return attrs


class LojaSerializer(BoundSerializer):
    tipo_catalogo = serializers.SerializerMethodField()

    def get_tipo_catalogo(self, obj):
        return obj.tipo_loja.modo_catalogo if obj.tipo_loja_id else "produtos"

    tipo_loja_nome = serializers.CharField(source="tipo_loja.nome", read_only=True, allow_null=True)
    binding = "dono"
    categorias = CategoriaSerializer(many=True, read_only=True)
    class Meta:
        model = Loja
        fields = ["id", "dono", "nome", "tipo_loja", "tipo_loja_nome", "tipo_catalogo", "email_contato", "whatsapp", "logo", "aberta", "permite_entrega", "permite_retirada", "cor_primaria", "cor_secundaria", "categorias", "ativa", "assinatura_status", "assinatura_valida_ate", "mensalidade", "meios_pagamento", "instrucoes_pagamento"]
        read_only_fields = ["dono", "ativa", "assinatura_status", "assinatura_valida_ate", "mensalidade"]


    def validate(self, attrs):
        attrs = super().validate(attrs)
        for name in ("ativa", "assinatura_status", "assinatura_valida_ate", "mensalidade"):
            if name in self.initial_data:
                raise serializers.ValidationError({name: "Somente o administrador pode alterar este campo."})
        return attrs

    def validate_meios_pagamento(self, value):
        allowed = {"pix", "dinheiro", "credito", "debito"}
        if not isinstance(value, list) or not value or any(not isinstance(item, str) or item not in allowed for item in value):
            raise serializers.ValidationError("Escolha pelo menos um meio: pix, dinheiro, credito, debito.")
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Não repita meios de pagamento.")
        return value

    def validate_instrucoes_pagamento(self, value):
        if len(value) > 2000:
            raise serializers.ValidationError("Limite de 2000 caracteres.")
        return value


class LojaPublicaSerializer(serializers.ModelSerializer):
    tipo_catalogo = serializers.SerializerMethodField()

    def get_tipo_catalogo(self, obj):
        return obj.tipo_loja.modo_catalogo if obj.tipo_loja_id else "produtos"

    tipo_loja_nome = serializers.CharField(source="tipo_loja.nome", read_only=True, allow_null=True)
    class Meta:
        model = Loja
        fields = ["id", "nome", "tipo_loja", "tipo_loja_nome", "tipo_catalogo", "email_contato", "whatsapp", "logo", "aberta", "permite_entrega", "permite_retirada", "cor_primaria", "cor_secundaria", "meios_pagamento", "instrucoes_pagamento"]


class TipoLojaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoLoja
        fields = ["id", "nome", "modo_catalogo"]
