from rest_framework.permissions import BasePermission
from reservastoresupa.lojas.models import Loja
from .models import Perfil


def papel_usuario(user):
    if user.is_staff:
        return "administrador"
    if Loja.objects.filter(dono=user).exists():
        return "lojista"
    return Perfil.objects.filter(user=user).values_list("papel", flat=True).first() or "cliente"


class ClientePermission(BasePermission):
    message = "Este recurso é exclusivo de clientes."
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and papel_usuario(request.user) == "cliente")


class LojistaPermission(BasePermission):
    message = "Este recurso é exclusivo de lojistas."
    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and papel_usuario(request.user) == "lojista")
