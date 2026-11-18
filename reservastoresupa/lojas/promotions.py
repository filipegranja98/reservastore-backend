from io import BytesIO
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from .models import Loja, Produto, Promocao
from .serializers import BoundSerializer
from .views import OwnedViewSet

class PromocaoSerializer(BoundSerializer):
    produto_nome = serializers.CharField(source="produto.nome", read_only=True, default="")
    preco_anterior = serializers.DecimalField(source="produto.preco", max_digits=10, decimal_places=2, read_only=True, default=None)
    class Meta:
        model = Promocao
        fields = ["id", "loja", "titulo", "descricao", "imagem", "validade", "ativa", "produto", "produto_nome", "preco_anterior", "preco_promocional"]
        read_only_fields = ["loja"]
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        request=self.context.get("request")
        self.fields["produto"].queryset=Produto.objects.filter(loja__dono=request.user, ativo=True) if request and request.user.is_authenticated else Produto.objects.none()
    def validate_validade(self,value):
        if value < timezone.localdate():
            raise ValidationError("Escolha hoje ou uma data futura para a validade.")
        return value
    def validate_imagem(self,value):
        if value is None: return value
        if value.size > 5*1024*1024: raise ValidationError("Escolha uma imagem de até 5 MB.")
        value.seek(0)
        with Image.open(value) as source:
            if source.format not in {"JPEG","PNG","WEBP"} or source.width*source.height>25000000:
                raise ValidationError("Use uma imagem JPG, PNG ou WebP de até 25 megapixels.")
            source.thumbnail((1600,1600))
            photo=ImageOps.exif_transpose(source).convert("RGB")
            output=BytesIO();photo.save(output,"JPEG",quality=85)
        return ContentFile(output.getvalue(),name="promocao.jpg")
    def validate(self,attrs):
        attrs=super().validate(attrs)
        if attrs.get("ativa") is False and set(attrs)=={"ativa"}: return attrs
        shop=Loja.objects.get(dono=self.context["request"].user)
        product=attrs.get("produto",getattr(self.instance,"produto",None))
        price=attrs.get("preco_promocional",getattr(self.instance,"preco_promocional",None))
        if shop.catalogo_efetivo=="servicos" and (product is not None or price is not None):
            raise ValidationError("Para serviços, descreva a oferta sem preço fixo. O valor será informado no orçamento.")
        if product and (product.loja_id!=shop.pk or product.categoria.loja_id!=shop.pk or not product.ativo):
            raise ValidationError({"produto":"Escolha um produto ativo desta loja."})
        if (product is None)!=(price is None):
            raise ValidationError("Para oferecer desconto, selecione o produto e informe o preço promocional.")
        if price is not None and (price<=0 or price>=product.preco):
            raise ValidationError({"preco_promocional":"O preço promocional deve ser maior que zero e menor que o preço atual do produto."})
        active=attrs.get("ativa",getattr(self.instance,"ativa",True))
        validity=attrs.get("validade",getattr(self.instance,"validade",None))
        if active and validity and validity < timezone.localdate(): raise ValidationError({"validade":"Atualize a validade antes de ativar esta promoção."})
        if product and active:
            others=Promocao.objects.filter(loja=shop,produto=product,ativa=True,validade__gte=timezone.localdate())
            if self.instance: others=others.exclude(pk=self.instance.pk)
            if others.exists(): raise ValidationError("Este produto já tem uma promoção ativa. Edite ou desative a anterior.")
        return attrs

class PromocaoViewSet(OwnedViewSet):
    serializer_class=PromocaoSerializer
    http_method_names=["get","post","patch","head","options"]
    def get_queryset(self):
        return super().get_queryset().select_related("produto")
    @transaction.atomic
    def create(self,*args,**kwargs):
        get_object_or_404(Loja.objects.select_for_update(),dono=self.request.user)
        return super().create(*args,**kwargs)
    @transaction.atomic
    def partial_update(self,*args,**kwargs):
        get_object_or_404(Loja.objects.select_for_update(),dono=self.request.user)
        return super().partial_update(*args,**kwargs)

def public_promotions(shop):
    rows=shop.promocoes.filter(ativa=True,validade__gte=timezone.localdate()).select_related("produto__categoria")
    if shop.catalogo_efetivo=="servicos": return rows.filter(produto__isnull=True,preco_promocional__isnull=True)
    return rows.filter(Q(produto__isnull=True,preco_promocional__isnull=True)|Q(produto__ativo=True,produto__loja_id=shop.pk,produto__categoria__loja_id=shop.pk,preco_promocional__gt=0,preco_promocional__lt=F("produto__preco")))
