from django.core.exceptions import ValidationError
from django.db import models
from .loja import Loja
from .categoria import Categoria


class Produto(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name="produtos")
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name="produtos")
    ativo = models.BooleanField(default=True)
    nome = models.CharField(max_length=255)
    preco = models.DecimalField(max_digits=10, decimal_places=2)
    imagem = models.ImageField(upload_to="produtos/", blank=True, null=True)

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        self.preco = self._meta.get_field("preco").to_python(self.preco)
        if self.categoria_id and self.loja_id and self.categoria.loja_id != self.loja_id:
            raise ValidationError({"categoria": "A categoria deve pertencer à mesma loja."})
        if self.preco is not None and self.preco < 0:
            raise ValidationError({"preco": "O preço não pode ser negativo."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
