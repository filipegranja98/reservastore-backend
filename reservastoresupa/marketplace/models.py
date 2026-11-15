import uuid
import unicodedata
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
from django.db import models
from django.db.models import Q
from reservastoresupa.lojas.models import Loja, Produto


class Agendamento(models.Model):
    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="agendamentos")
    loja = models.ForeignKey(Loja, on_delete=models.PROTECT, related_name="agendamentos")
    servico = models.ForeignKey(Produto, on_delete=models.PROTECT)
    chave = models.UUIDField(unique=True)
    servico_nome = models.CharField(max_length=255)
    valor_referencia = models.DecimalField(max_digits=10, decimal_places=2)
    endereco = models.JSONField()
    inicio_solicitado = models.DateTimeField()
    inicio_proposto = models.DateTimeField(null=True, blank=True)
    inicio_confirmado = models.DateTimeField(null=True, blank=True)
    observacoes = models.TextField(blank=True, max_length=1500)
    mensagem_loja = models.TextField(blank=True, max_length=1000)
    status = models.CharField(max_length=20, default="solicitado", choices=[(v, v) for v in ("solicitado", "contraproposta", "confirmado", "concluido", "recusado", "cancelado")])
    versao = models.PositiveIntegerField(default=1)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em", "-pk"]
        constraints = [models.UniqueConstraint(fields=["loja", "inicio_confirmado"], condition=Q(status="confirmado"), name="agendamento_horario_confirmado_unico")]


def normalizar_condominio(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class Perfil(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil")
    papel = models.CharField(max_length=10, choices=[("cliente", "Cliente"), ("lojista", "Lojista")], default="cliente")
    telefone = models.CharField(max_length=20, blank=True)


class Endereco(models.Model):
    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enderecos")
    condominio = models.CharField(max_length=150)
    bloco = models.CharField(max_length=40)
    apartamento = models.CharField(max_length=40)
    destinatario = models.CharField(max_length=150)
    telefone = models.CharField(max_length=20)
    complemento = models.CharField(max_length=300, blank=True)


class AreaEntrega(models.Model):
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE, related_name="areas_entrega")
    condominio = models.CharField(max_length=150)
    condominio_normalizado = models.CharField(max_length=450, editable=False)
    taxa = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    ativa = models.BooleanField(default=True)
    prazo_estimado_minutos = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(32767)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["loja", "condominio_normalizado"], name="area_unica_por_loja"),
                       models.CheckConstraint(condition=Q(taxa__gte=0), name="taxa_entrega_nao_negativa"),
                       models.CheckConstraint(condition=Q(prazo_estimado_minutos__isnull=True) | Q(prazo_estimado_minutos__gte=1, prazo_estimado_minutos__lte=32767), name="area_prazo_positivo")]

    def save(self, *args, **kwargs):
        self.condominio_normalizado = normalizar_condominio(self.condominio)
        super().save(*args, **kwargs)


class Carrinho(models.Model):
    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="carrinhos")
    loja = models.ForeignKey(Loja, on_delete=models.CASCADE)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["cliente", "loja"], name="carrinho_cliente_loja_unico")]


class ItemCarrinho(models.Model):
    carrinho = models.ForeignKey(Carrinho, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    quantidade = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["carrinho", "produto"], name="produto_unico_no_carrinho"),
                       models.CheckConstraint(condition=Q(quantidade__gte=1, quantidade__lte=99), name="quantidade_carrinho_valida")]


class Pedido(models.Model):
    STATUS = [(v, v.replace("_", " ").capitalize()) for v in
              ("recebido", "aceito", "preparando", "pronto_retirada", "saiu_entrega", "entregue", "cancelado")]
    PAGAMENTOS = [(v, v.capitalize()) for v in ("pendente", "informado", "confirmado", "estornado")]
    chave_checkout = models.UUIDField(null=True, blank=True, editable=False)
    codigo = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="pedidos")
    loja = models.ForeignKey(Loja, on_delete=models.PROTECT, related_name="pedidos")
    status = models.CharField(max_length=15, choices=STATUS, default="recebido")
    modalidade = models.CharField(max_length=8, choices=[("entrega", "Entrega"), ("retirada", "Retirada na loja")], default="entrega")
    pagamento_status = models.CharField(max_length=12, choices=PAGAMENTOS, default="pendente")
    meio_pagamento = models.CharField(max_length=30)
    precisa_troco = models.BooleanField(default=False)
    troco_para = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    instrucoes_pagamento = models.TextField(blank=True)
    endereco = models.JSONField()
    observacoes = models.CharField(max_length=1000, blank=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    taxa_entrega = models.DecimalField(max_digits=10, decimal_places=2)
    prazo_estimado_minutos = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(32767)])
    total = models.DecimalField(max_digits=14, decimal_places=2)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em", "-pk"]
        constraints = [models.UniqueConstraint(fields=["cliente", "chave_checkout"], name="checkout_unico_por_cliente"),
                       models.CheckConstraint(condition=Q(subtotal__gte=0, taxa_entrega__gte=0, total__gte=0), name="pedido_valores_nao_negativos"),
                       models.CheckConstraint(condition=Q(prazo_estimado_minutos__isnull=True) | Q(prazo_estimado_minutos__gte=1, prazo_estimado_minutos__lte=32767), name="pedido_prazo_positivo")]


class ItemPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey(Produto, on_delete=models.SET_NULL, null=True)
    nome = models.CharField(max_length=255)
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    quantidade = models.PositiveSmallIntegerField()
    total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantidade__gte=1, quantidade__lte=99, preco_unitario__gte=0, total__gte=0), name="item_pedido_valores_validos")]


class EventoPedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name="eventos")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    tipo = models.CharField(max_length=15, choices=[("status", "Status"), ("pagamento", "Pagamento")])
    anterior = models.CharField(max_length=20, blank=True)
    novo = models.CharField(max_length=20)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criado_em", "pk"]
