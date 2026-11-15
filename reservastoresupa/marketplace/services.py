from dataclasses import dataclass
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from reservastoresupa.lojas.models import Loja, Produto
from .models import Carrinho, ItemCarrinho, Endereco, AreaEntrega, Pedido, ItemPedido, EventoPedido, normalizar_condominio

TRANSICOES = {"recebido": {"aceito", "cancelado"}, "aceito": {"preparando", "cancelado"},
              "preparando": {"saiu_entrega", "pronto_retirada", "cancelado"}, "pronto_retirada": {"entregue", "cancelado"}, "saiu_entrega": {"entregue"},
              "entregue": set(), "cancelado": set()}


def bloquear_cliente(user):
    # A single lock order serializes cart mutations and checkout for this customer on PostgreSQL.
    get_user_model().objects.select_for_update().get(pk=user.pk)


@transaction.atomic
def adicionar_item(user, loja_id, produto_id, quantidade):
    bloquear_cliente(user)
    loja = get_object_or_404(Loja.objects.select_for_update(), pk=loja_id)
    if not loja.aberta:
        raise ValidationError("Esta loja está fechada no momento e não está recebendo novos pedidos.")
    if not loja.aceita_pedidos:
        raise ValidationError("Esta loja não está disponível para pedidos.")
    produto = get_object_or_404(Produto.objects.select_for_update(), pk=produto_id, loja=loja, ativo=True)
    if produto.categoria.loja_id != loja.pk:
        raise ValidationError("Produto com categoria inconsistente. Contate a loja.")
    carrinho, _ = Carrinho.objects.get_or_create(cliente=user, loja=loja)
    if not carrinho.itens.filter(produto=produto).exists() and carrinho.itens.count() >= 100:
        raise ValidationError("Limite de 100 produtos distintos por carrinho.")
    ItemCarrinho.objects.update_or_create(carrinho=carrinho, produto=produto, defaults={"quantidade": quantidade})
    carrinho.save(update_fields=["atualizado_em"])
    return carrinho


@dataclass
class CompraPreparada:
    loja: Loja
    carrinho: Carrinho
    endereco: Endereco | None
    area: AreaEntrega | None
    itens: list
    subtotal: Decimal

    @property
    def total(self):
        return self.subtotal + (self.area.taxa if self.area else Decimal("0.00"))

    def snapshot_endereco(self):
        if self.endereco is None:
            return {}
        return {field: getattr(self.endereco, field) for field in
                ("condominio", "bloco", "apartamento", "destinatario", "telefone", "complemento")}


def _preparar_compra(user, attrs):
    """Shared validation/calculation; callers must hold the customer lock in a transaction."""
    loja = get_object_or_404(Loja.objects.select_for_update(), pk=attrs["loja"])
    if not loja.aberta:
        raise ValidationError("Esta loja está fechada no momento e não está recebendo novos pedidos.")
    if not loja.aceita_pedidos:
        raise ValidationError("Esta loja não está disponível para pedidos.")
    carrinho = get_object_or_404(Carrinho.objects.select_for_update(), cliente=user, loja=loja)
    itens = list(carrinho.itens.all())
    if not itens:
        raise ValidationError("Carrinho vazio.")
    produtos = Produto.objects.select_for_update().filter(pk__in=[item.produto_id for item in itens]).in_bulk()
    modalidade = attrs.get("modalidade", "entrega")
    if (modalidade == "entrega" and not loja.permite_entrega) or (modalidade == "retirada" and not loja.permite_retirada):
        raise ValidationError("Esta modalidade está desativada pela loja. Escolha outra opção disponível.")
    endereco = area = None
    if attrs.get("modalidade", "entrega") == "retirada":
        if loja.tipo_loja_id and loja.tipo_loja.modo_catalogo == "servicos":
            raise ValidationError("Retirada está disponível somente para lojas de produtos.")
    else:
        endereco = get_object_or_404(Endereco.objects.select_for_update(), pk=attrs["endereco"], cliente=user)
        area = get_object_or_404(AreaEntrega.objects.select_for_update(), pk=attrs["area_entrega"], loja=loja, ativa=True)
        if normalizar_condominio(endereco.condominio) != area.condominio_normalizado:
            raise ValidationError({"area_entrega": "O condomínio do endereço está fora desta área de entrega."})
    if attrs["meio_pagamento"] not in loja.meios_pagamento:
        raise ValidationError({"meio_pagamento": "Meio de pagamento não aceito nesta loja."})
    subtotal = Decimal("0.00")
    snapshots = []
    for item in itens:
        produto = produtos.get(item.produto_id)
        if not produto or not produto.ativo or produto.loja_id != loja.pk or produto.categoria.loja_id != loja.pk:
            raise ValidationError("Um produto do carrinho não está mais disponível nesta loja.")
        if produto.preco < 0:
            raise ValidationError("Produto com preço inválido.")
        total = (produto.preco * item.quantidade).quantize(Decimal("0.01"))
        subtotal += total
        snapshots.append({"produto": produto, "nome": produto.nome, "preco_unitario": produto.preco,
                          "quantidade": item.quantidade, "total": total})
    if subtotal + (area.taxa if area else Decimal("0.00")) > Decimal("999999999999.99"):
        raise ValidationError("O total excede o limite do pedido.")
    total = subtotal + (area.taxa if area else Decimal("0.00"))
    if attrs.get("precisa_troco") and attrs["troco_para"] < total:
        raise ValidationError({"troco_para":"O valor informado para troco deve cobrir o total do pedido, incluindo a entrega."})
    return CompraPreparada(loja, carrinho, endereco, area, snapshots, subtotal)


@transaction.atomic
def previa_checkout(user, attrs):
    bloquear_cliente(user)
    compra = _preparar_compra(user, attrs)
    return {
        "loja": compra.loja.pk, "loja_nome": compra.loja.nome,
        "modalidade": attrs.get("modalidade", "entrega"),
        "area_entrega": compra.area.pk if compra.area else None,
        "endereco": {"id": compra.endereco.pk, **compra.snapshot_endereco()} if compra.endereco else None,
        "meio_pagamento": attrs["meio_pagamento"],
        "precisa_troco": attrs.get("precisa_troco", False), "troco_para": attrs.get("troco_para"),
        "valor_troco": attrs["troco_para"] - compra.total if attrs.get("precisa_troco") else None,
        "instrucoes_pagamento": compra.loja.instrucoes_pagamento,
        "itens": [{**item, "produto": item["produto"].pk} for item in compra.itens],
        "subtotal": compra.subtotal, "taxa_entrega": compra.area.taxa if compra.area else Decimal("0.00"),
        "total": compra.total, "prazo_estimado_minutos": compra.area.prazo_estimado_minutos if compra.area else None,
    }


@transaction.atomic
def checkout(user, attrs):
    bloquear_cliente(user)
    if attrs.get("chave_checkout"):
        existente = Pedido.objects.filter(cliente=user, chave_checkout=attrs["chave_checkout"]).first()
        if existente:
            if existente.loja_id != attrs["loja"]:
                raise ValidationError({"chave_checkout": "Esta chave já foi usada em outra loja."})
            return existente, False
    compra = _preparar_compra(user, attrs)
    pedido = Pedido.objects.create(
        cliente=user, loja=compra.loja, modalidade=attrs.get("modalidade", "entrega"), chave_checkout=attrs.get("chave_checkout"),
        precisa_troco=attrs.get("precisa_troco", False), troco_para=attrs.get("troco_para"),
        meio_pagamento=attrs["meio_pagamento"], instrucoes_pagamento=compra.loja.instrucoes_pagamento,
        endereco=compra.snapshot_endereco() if compra.endereco else {"condominio":"", "bloco":"", "apartamento":"", "complemento":"", "destinatario": user.get_full_name() or user.username, "telefone": user.perfil.telefone}, observacoes=attrs.get("observacoes", ""),
        subtotal=compra.subtotal, taxa_entrega=compra.area.taxa if compra.area else Decimal("0.00"), total=compra.total,
        prazo_estimado_minutos=compra.area.prazo_estimado_minutos if compra.area else None)
    ItemPedido.objects.bulk_create([ItemPedido(pedido=pedido, **snapshot) for snapshot in compra.itens])
    EventoPedido.objects.create(pedido=pedido, autor=user, tipo="status", anterior="", novo="recebido")
    compra.carrinho.delete()
    return pedido, True


@transaction.atomic
def mudar_status(user, pk, destino, lojista=False):
    qs = Pedido.objects.select_for_update()
    qs = qs.filter(loja__dono=user) if lojista else qs.filter(cliente=user)
    pedido = get_object_or_404(qs, pk=pk)
    if not lojista:
        if destino == "entregue" and pedido.status == "entregue":
            return pedido  # Safe retry after a lost confirmation response.
        can_receive = destino == "entregue" and (
            (pedido.modalidade == "entrega" and pedido.status == "saiu_entrega") or
            (pedido.modalidade == "retirada" and pedido.status == "pronto_retirada"))
        if not ((pedido.status == "recebido" and destino == "cancelado") or can_receive):
            raise ValidationError("Não é possível confirmar recebimento ou cancelar nesta etapa do pedido.")
    if (pedido.modalidade == "retirada" and destino == "saiu_entrega") or (pedido.modalidade == "entrega" and destino == "pronto_retirada"):
        raise ValidationError("Situação incompatível com a modalidade do pedido.")
    if destino not in TRANSICOES[pedido.status]:
        raise ValidationError("Transição de pedido não permitida.")
    anterior = pedido.status
    pedido.status = destino
    pedido.save(update_fields=["status", "atualizado_em"])
    EventoPedido.objects.create(pedido=pedido, autor=user, tipo="status", anterior=anterior, novo=destino)
    return pedido


@transaction.atomic
def mudar_pagamento(user, pk, destino, lojista=False):
    qs = Pedido.objects.select_for_update()
    qs = qs.filter(loja__dono=user) if lojista else qs.filter(cliente=user)
    pedido = get_object_or_404(qs, pk=pk)
    anterior = pedido.pagamento_status
    if lojista:
        valido = (destino == "confirmado" and anterior in {"pendente", "informado"} and pedido.status != "cancelado") or (destino == "estornado" and anterior == "confirmado")
    else:
        valido = destino == "informado" and anterior == "pendente" and pedido.status != "cancelado"
    if not valido:
        raise ValidationError("Transição de pagamento não permitida.")
    pedido.pagamento_status = destino
    pedido.save(update_fields=["pagamento_status", "atualizado_em"])
    EventoPedido.objects.create(pedido=pedido, autor=user, tipo="pagamento", anterior=anterior, novo=destino)
    return pedido
