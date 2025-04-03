from django.db import models
from django.contrib.auth.models import User  # Importando o modelo User para o dono da loja

class Loja(models.Model):
    dono = models.OneToOneField(User, on_delete=models.CASCADE)  # Definindo um valor padrão
    nome = models.CharField(max_length=100)
    whatsapp = models.CharField(max_length=20)
    logo = models.ImageField(upload_to='logos/', null=True, blank=True)
    def __str__(self):
        return self.nome
