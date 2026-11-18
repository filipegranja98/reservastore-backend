from django.db.models import Prefetch
from django.utils import timezone
from .models import Promocao

def vigentes():
    return Promocao.objects.filter(ativa=True, validade__gte=timezone.localdate())

def with_promotions(products):
    return products.select_related("loja__tipo_loja").prefetch_related(Prefetch("promocoes", queryset=vigentes(), to_attr="ofertas_vigentes"))

def current_price(product):
    if product.loja.catalogo_efetivo != "produtos":
        return product.preco
    offers = getattr(product, "ofertas_vigentes", None)
    if offers is None:
        offers = vigentes().filter(produto=product, loja_id=product.loja_id)
    return min([product.preco] + [offer.preco_promocional for offer in offers if offer.loja_id == product.loja_id and offer.preco_promocional is not None and 0 < offer.preco_promocional < product.preco])
