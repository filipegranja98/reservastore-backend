from .deployment_views import health, public_image
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
urlpatterns = [
    path("api/health/", health),
    path("media/<path:asset>", public_image),
    path("admin/", admin.site.urls),
    path("api/", include("reservastoresupa.marketplace.urls")),
    path("", include("reservastoresupa.lojas.urls")),
]
if settings.DEBUG:  # Somente no ambiente de desenvolvimento
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)