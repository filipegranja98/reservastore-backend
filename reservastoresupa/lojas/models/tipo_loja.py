from django.db import models


class TipoLoja(models.Model):
    modo_catalogo = models.CharField(max_length=10, choices=[("produtos", "Produtos"), ("servicos", "Serviços")], default="produtos")
    nome = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["nome", "pk"]
        verbose_name = "Tipo de loja"
        verbose_name_plural = "Tipos de loja"

    def __str__(self):
        return self.nome
