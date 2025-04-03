from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LojaViewSet, ProdutoViewSet, CategoriaViewSet, TodasLojasView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from .views import LogoutView
from django.conf import settings
from django.conf.urls.static import static

# Criação do router para os viewsets
router = DefaultRouter()
router.register(r'lojas', LojaViewSet, basename='loja')
router.register(r'produtos', ProdutoViewSet, basename='produto')
router.register(r'categorias', CategoriaViewSet, basename='categoria')

# URLpatterns
urlpatterns = [
    path('api/', include(router.urls)),  # Roteia as URLs dos viewsets

    # Endpoints específicos
    path('api/lojas/minha_loja', LojaViewSet.as_view({'get': 'minha_loja'}), name='minha_loja'),
    path('api/lojas/minha_loja_completa', LojaViewSet.as_view({'get': 'minha_loja_completa'}), name='minha_loja_completa'),
    path('api/lojas/todas_lojas', TodasLojasView.as_view(), name='todas_lojas'),

    # Endpoints de autenticação com JWT
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),  # Obter token
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),  # Renovar token
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),  # Verificar token
    path('api/token/logout/', LogoutView.as_view(), name='logout'),  # Logout (opcional, se você implementar o logout)

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)  # Serve arquivos de mídia (se necessário)

# Configuração para servir arquivos de mídia durante o desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
