from django.db import models
from .loja import Loja


class Categoria(models.Model):
    nome = models.CharField(max_length=100)
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name="categorias", null=True, blank=True)

    def __str__(self):
        loja = self.loja.nome if self.loja_id else "Sem loja"
        return f"{self.nome} - {loja}"
