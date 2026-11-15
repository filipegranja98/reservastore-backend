from .password_recovery import PasswordRecoveryRequest, PasswordRecoveryConfirm
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (CadastroView, ContaView, SenhaView, EnderecoViewSet, AreaEntregaViewSet, CatalogoViewSet, TipoLojaViewSet,
    CarrinhosView, CarrinhoView, ItensCarrinhoView, ItemCarrinhoView, PedidoViewSet,
    PedidosLojistaViewSet, LojasAdminViewSet, PedidosAdminViewSet, UsuariosAdminViewSet)

router = DefaultRouter()
router.register("enderecos", EnderecoViewSet, basename="endereco")
router.register("lojista/areas-entrega", AreaEntregaViewSet, basename="area-entrega")
router.register("catalogo/tipos-loja", TipoLojaViewSet, basename="tipo-loja")
router.register("catalogo/lojas", CatalogoViewSet, basename="catalogo")
router.register("pedidos", PedidoViewSet, basename="pedido")
router.register("lojista/pedidos", PedidosLojistaViewSet, basename="pedido-lojista")
router.register("administracao/lojas", LojasAdminViewSet, basename="loja-admin")
router.register("administracao/pedidos", PedidosAdminViewSet, basename="pedido-admin")
router.register("administracao/usuarios", UsuariosAdminViewSet, basename="usuario-admin")
urlpatterns = [
    path("auth/recuperar-senha/", PasswordRecoveryRequest.as_view()),
    path("auth/redefinir-senha/", PasswordRecoveryConfirm.as_view()),
    path("auth/cadastro/", CadastroView.as_view()),
    path("conta/", ContaView.as_view()),
    path("conta/senha/", SenhaView.as_view()),
    path("carrinhos/", CarrinhosView.as_view()),
    path("carrinhos/<int:loja_id>/", CarrinhoView.as_view()),
    path("carrinhos/<int:loja_id>/itens/", ItensCarrinhoView.as_view()),
    path("carrinhos/<int:loja_id>/itens/<int:pk>/", ItemCarrinhoView.as_view()),
    path("", include(router.urls)),
]
