import uuid
from django.db import models

def promocao_imagem(instance, filename):
    return f"promocoes/{uuid.uuid4().hex}.jpg"

class Promocao(models.Model):
    loja = models.ForeignKey("lojas.Loja", on_delete=models.CASCADE, related_name="promocoes")
    titulo = models.CharField(max_length=100)
    descricao = models.TextField(blank=True, max_length=1000)
    imagem = models.ImageField(upload_to=promocao_imagem, blank=True, null=True)
    validade = models.DateField()
    ativa = models.BooleanField(default=True)
    produto = models.ForeignKey("lojas.Produto", on_delete=models.CASCADE, related_name="promocoes", blank=True, null=True)
    preco_promocional = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-atualizado_em", "-pk"]
        indexes = [models.Index(fields=["loja", "ativa", "validade"], name="promocao_loja_vigencia")]
        constraints = [models.CheckConstraint(condition=models.Q(preco_promocional__isnull=True) | models.Q(preco_promocional__gt=0, produto__isnull=False), name="promocao_preco_positivo")]
