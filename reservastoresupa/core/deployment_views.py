from pathlib import Path

from django.conf import settings
from django.db import connection
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})


@require_safe
def public_image(request, asset):
    root = Path(settings.MEDIA_ROOT).resolve()
    target = (root / asset).resolve()
    if not target.is_relative_to(root) or target.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"} or not target.is_file():
        raise Http404
    response = FileResponse(target.open("rb"))
    response["X-Content-Type-Options"] = "nosniff"
    return response
