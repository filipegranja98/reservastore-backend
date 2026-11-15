from django.db import models
from django.core.validators import MinValueValidator, RegexValidator
from django.contrib.auth.models import User
from django.utils import timezone


def meios_padrao():
    return ["pix", "dinheiro"]


def lojas_publicas():
    return Loja.objects.filter(ativa=True, assinatura_status="ativa").filter(
        models.Q(assinatura_valida_ate__isnull=True) | models.Q(assinatura_valida_ate__gte=timezone.localdate()))


class Loja(models.Model):
    dono = models.OneToOneField(User, on_delete=models.CASCADE)
    nome = models.CharField(max_length=100)
    tipo_loja = models.ForeignKey("TipoLoja", on_delete=models.PROTECT, null=True, blank=True, related_name="lojas", verbose_name="Tipo de loja")
    email_contato = models.EmailField(blank=True, default="", verbose_name="Email da loja ou do proprietário", help_text="Email público de contato. Pode ser o email comercial da loja ou do dono.")
    whatsapp = models.CharField(max_length=20, verbose_name="Telefone / WhatsApp da loja", help_text="Informe o número próprio da loja com DDD; inclua o DDI se for de outro país.")
    logo = models.ImageField(upload_to="logos/", null=True, blank=True)
    cor_primaria = models.CharField(max_length=7, default="#17624E", validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Use uma cor no formato #RRGGBB.")], help_text="Cor dos botões, cabeçalho e carrinho. Ex.: #17624E")
    cor_secundaria = models.CharField(max_length=7, default="#EAF1E9", validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Use uma cor no formato #RRGGBB.")], help_text="Cor complementar da loja. Ex.: #EAF1E9")
    permite_entrega = models.BooleanField(default=True, verbose_name="Permite entrega")
    permite_retirada = models.BooleanField(default=False, verbose_name="Permite retirada no local")
    aberta = models.BooleanField(default=False, verbose_name="Aberta para atendimento", help_text="Marque quando estiver operando e recebendo novos pedidos. Fechada continua visível no catálogo aprovado.")
    ativa = models.BooleanField(default=False)
    assinatura_status = models.CharField(max_length=12, default="pendente", choices=[
        ("pendente", "Pendente"), ("ativa", "Ativa"), ("suspensa", "Suspensa"), ("cancelada", "Cancelada")])
    assinatura_valida_ate = models.DateField(null=True, blank=True)
    mensalidade = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    meios_pagamento = models.JSONField(default=meios_padrao)
    instrucoes_pagamento = models.TextField(blank=True, max_length=2000)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(mensalidade__isnull=True) | models.Q(mensalidade__gte=0), name="mensalidade_nao_negativa")]

    @property
    def aceita_pedidos(self):
        return self.aberta and self.ativa and self.assinatura_status == "ativa" and (
            self.assinatura_valida_ate is None or self.assinatura_valida_ate >= timezone.localdate())

    def __str__(self):
        return self.nome
