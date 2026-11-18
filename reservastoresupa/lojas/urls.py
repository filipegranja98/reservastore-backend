from .promotions import PromocaoViewSet
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import LojaViewSet, ProdutoViewSet, CategoriaViewSet, TodasLojasView, LogoutView
from reservastoresupa.marketplace.authentication import LoginView, RefreshView, VerifyView

router = DefaultRouter()
router.register("lojas", LojaViewSet, basename="loja")
router.register("produtos", ProdutoViewSet, basename="produto")
router.register("promocoes", PromocaoViewSet, basename="promocao")
router.register("categorias", CategoriaViewSet, basename="categoria")

urlpatterns = [
    path("api/", include(router.urls)),
    path("api/lojas/minha_loja", LojaViewSet.as_view({"get": "minha_loja"}), name="minha_loja"),
    path("api/lojas/minha_loja_completa", LojaViewSet.as_view({"get": "minha_loja_completa"}), name="minha_loja_completa"),
    path("api/lojas/todas_lojas", TodasLojasView.as_view(), name="todas_lojas"),
    path("api/token/", LoginView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", RefreshView.as_view(), name="token_refresh"),
    path("api/token/verify/", VerifyView.as_view(), name="token_verify"),
    path("api/token/logout/", LogoutView.as_view(), name="logout"),
]
