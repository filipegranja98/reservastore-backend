from django.db import models
from .loja import Loja  # Importa o modelo Loja
from .categoria import Categoria  # Importa o modelo Categoria
from django.core.exceptions import ValidationError

class Produto(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name="produtos")
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name="produtos")
    nome = models.CharField(max_length=255)
    preco = models.DecimalField(max_digits=10, decimal_places=2)
    imagem = models.ImageField(upload_to="produtos/", blank=True, null=True)

    def __str__(self):
        return self.nome

    def clean(self):
        # Verificar se o preço é negativo
        if self.preco < 0:
            raise ValidationError({'preco': 'O preço não pode ser negativo.'})

    def save(self, *args, **kwargs):
        # Chama o método clean antes de salvar
        self.clean()
        super().save(*args, **kwargs)
