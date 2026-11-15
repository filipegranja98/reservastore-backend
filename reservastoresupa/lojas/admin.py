from .forms import LojaAdminForm
from django.contrib import admin
from .models import Loja, Categoria, Produto, TipoLoja


@admin.register(Loja)
class LojaAdmin(admin.ModelAdmin):
    form = LojaAdminForm
    list_display = ("nome", "aberta", "ativa", "assinatura_status", "cor_primaria", "cor_secundaria")
    list_filter = ("tipo_loja", "aberta", "ativa", "assinatura_status")
    fieldsets = (
        ("Loja", {"fields": ("nome", "dono", "email_contato", "whatsapp", "modalidade_catalogo", "tipo_loja")}),
        ("Atendimento", {"fields": ("aberta", "permite_entrega", "permite_retirada"), "description": "Estado operacional manual, separado da aprovação e assinatura da loja."}),
        ("Identidade visual", {"fields": ("logo", "cor_primaria", "cor_secundaria"), "description": "Logo e cores aplicados somente a esta loja no aplicativo."}),
        ("Pagamento direto", {"fields": ("meios_pagamento", "instrucoes_pagamento")}),
        ("Aprovação e assinatura", {"fields": ("ativa", "assinatura_status", "assinatura_valida_ate", "mensalidade")}),
    )


admin.site.register(Categoria)
admin.site.register(Produto)

admin.site.register(TipoLoja)
