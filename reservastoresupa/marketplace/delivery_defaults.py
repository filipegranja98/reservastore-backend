from decimal import Decimal
from django.db import transaction
from .condominiums import CONDOMINIOS_RESERVA
from .models import AreaEntrega, normalizar_condominio

@transaction.atomic
def ensure_reserva_areas(shop, using="default"):
    for name in CONDOMINIOS_RESERVA:
        area, created = AreaEntrega.objects.using(using).get_or_create(
            loja_id=shop.pk, condominio_normalizado=normalizar_condominio(name),
            defaults={"condominio":name,"taxa":Decimal("0.00"),"ativa":True})
        if not created and not area.ativa:
            area.ativa=True
            area.save(using=using,update_fields=["ativa"])
