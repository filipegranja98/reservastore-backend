from django.db import models
from .loja import Loja  # Importando o modelo Loja

class Categoria(models.Model):
    nome = models.CharField(max_length=100)
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name="categorias", null=True, blank=True)

    def __str__(self):
        return f"{self.nome} - {self.loja.nome}"
