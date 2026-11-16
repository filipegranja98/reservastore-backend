import base64
from io import BytesIO
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
from rest_framework import serializers
from .serializers import StrictSerializer


class PhotoInput(StrictSerializer):
    imagem = serializers.ImageField()
    chave = serializers.UUIDField()

    def validate_imagem(self, value):
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Cada foto deve ter até 5 MB.")
        value.seek(0)
        with Image.open(value) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"} or source.width * source.height > 25000000:
                raise serializers.ValidationError("Use uma foto JPG, PNG ou WebP de até 25 megapixels.")
            photo = ImageOps.exif_transpose(source).convert("RGB")
            photo.thumbnail((1600, 1600))
            output = BytesIO()
            photo.save(output, "JPEG", quality=85, optimize=True)
        return ContentFile(output.getvalue(), name="estofado.jpg")


def preview(photo):
    with photo.imagem.open("rb") as stream, Image.open(stream) as source:
        source.thumbnail((1024, 1024))
        output = BytesIO()
        source.convert("RGB").save(output, "JPEG", quality=78)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")
