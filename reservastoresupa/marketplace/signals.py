from django.db.models.signals import post_save
from django.dispatch import receiver
from reservastoresupa.lojas.models import Loja
from .delivery_defaults import ensure_reserva_areas

@receiver(post_save, sender=Loja, dispatch_uid="reserva_default_delivery_areas")
def create_delivery_areas(sender, instance, created, raw=False, using="default", **kwargs):
    if created and not raw:
        ensure_reserva_areas(instance, using=using)
