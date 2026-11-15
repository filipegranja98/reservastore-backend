from django.contrib import admin
from .models import Perfil, Endereco, AreaEntrega, Carrinho, Pedido, ItemPedido, EventoPedido, Agendamento

admin.site.register(Perfil)
admin.site.register(Endereco)
admin.site.register(AreaEntrega)


@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ["id", "loja", "cliente", "servico_nome", "status", "inicio_solicitado", "inicio_confirmado"]
    list_filter = ["status", "loja"]
    readonly_fields = [field.name for field in Agendamento._meta.fields]
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ["codigo", "loja", "status", "pagamento_status", "total", "criado_em"]
    list_filter = ["status", "pagamento_status", "loja"]
    readonly_fields = [field.name for field in Pedido._meta.fields]
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EventoPedido)
class EventoPedidoAdmin(admin.ModelAdmin):
    readonly_fields = [field.name for field in EventoPedido._meta.fields]
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
