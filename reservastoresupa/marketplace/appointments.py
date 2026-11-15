from datetime import timedelta
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from reservastoresupa.lojas.models import Loja, Produto
from reservastoresupa.lojas.models.loja import lojas_publicas
from .models import Agendamento, Endereco
from .permissions import papel_usuario
from .pagination import OptionalPageNumberPagination
from .serializers import StrictSerializer


def validate_future(value):
    if not timezone.now() < value <= timezone.now() + timedelta(days=365):
        raise ValidationError("Escolha uma data futura, nos próximos 12 meses.")
    return value


class BookingOutput(serializers.ModelSerializer):
    loja_nome = serializers.CharField(source="loja.nome", read_only=True)
    cliente_nome = serializers.SerializerMethodField()

    def get_cliente_nome(self, obj):
        return obj.cliente.get_full_name() or obj.cliente.username

    class Meta:
        model = Agendamento
        fields = ["id", "loja", "loja_nome", "cliente_nome", "servico", "servico_nome", "valor_referencia", "endereco", "inicio_solicitado", "inicio_proposto", "inicio_confirmado", "observacoes", "mensagem_loja", "status", "versao", "criado_em"]


class BookingInput(StrictSerializer):
    servico = serializers.IntegerField(min_value=1)
    endereco = serializers.IntegerField(min_value=1)
    inicio_solicitado = serializers.DateTimeField()
    observacoes = serializers.CharField(max_length=1500, allow_blank=True, default="")
    chave = serializers.UUIDField()

    def validate_inicio_solicitado(self, value):
        return validate_future(value)


class BookingAction(StrictSerializer):
    acao = serializers.ChoiceField(choices=["confirmar", "propor", "aceitar_proposta", "recusar", "cancelar", "concluir"])
    versao = serializers.IntegerField(min_value=1)
    inicio_proposto = serializers.DateTimeField(required=False)
    mensagem = serializers.CharField(max_length=1000, allow_blank=True, default="")


class AgendamentoViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = BookingOutput
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        user = self.request.user
        qs = Agendamento.objects.filter(Q(cliente=user) | Q(loja__dono=user)).select_related("loja", "cliente")
        state = self.request.query_params.get("status")
        if self.action == "list":
            if state == "pendentes":
                qs = qs.filter(status__in=["solicitado", "contraproposta"])
            elif state == "historico":
                qs = qs.filter(status__in=["concluido", "recusado", "cancelado"])
            elif state == "confirmado":
                qs = qs.filter(status=state).order_by("inicio_confirmado", "pk")
        return qs

    @transaction.atomic
    def create(self, request):
        if papel_usuario(request.user) != "cliente":
            raise PermissionDenied("Entre com uma conta de cliente para agendar.")
        data = BookingInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        item = get_object_or_404(Produto.objects.select_related("loja__tipo_loja"), pk=values["servico"], ativo=True)
        loja = Loja.objects.select_for_update().get(pk=item.loja_id)
        previous = Agendamento.objects.filter(cliente=request.user, chave=values["chave"]).first()
        if previous:
            return Response(BookingOutput(previous).data)
        if loja.catalogo_efetivo != "servicos" or not lojas_publicas().filter(pk=loja.pk).exists():
            raise ValidationError("Esta loja não está disponível para agendamento de serviços.")
        address = get_object_or_404(Endereco, pk=values["endereco"], cliente=request.user)
        if not all(getattr(address, field).strip() for field in ("condominio", "bloco", "apartamento", "destinatario", "telefone")):
            raise ValidationError("Complete seu endereço e telefone antes de agendar.")
        try:
            with transaction.atomic():
                booking = Agendamento.objects.create(cliente=request.user, loja=loja, servico=item,
                    chave=values["chave"], servico_nome=item.nome, valor_referencia=item.preco,
                    endereco={f: getattr(address, f) for f in ("condominio", "bloco", "apartamento", "destinatario", "telefone", "complemento")},
                    inicio_solicitado=values["inicio_solicitado"], observacoes=values["observacoes"])
        except IntegrityError:
            raise ValidationError("Solicitação repetida. Atualize seus agendamentos antes de enviar novamente.")
        return Response(BookingOutput(booking).data, status=201)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def responder(self, request, pk=None):
        # Every confirmation for a shop holds the same lock before checking its time slots.
        initial = get_object_or_404(self.get_queryset(), pk=pk)
        loja = Loja.objects.select_for_update().get(pk=initial.loja_id)
        booking = Agendamento.objects.select_for_update().select_related("loja", "cliente").get(pk=initial.pk)
        data = BookingAction(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        if values["versao"] != booking.versao:
            raise ValidationError("Este agendamento mudou. Atualize antes de responder.")
        merchant = loja.dono_id == request.user.pk
        action_name = values["acao"]
        if action_name in {"confirmar", "propor", "recusar", "concluir"} and not merchant:
            raise PermissionDenied("Somente a loja pode realizar esta ação.")
        if action_name == "aceitar_proposta" and (merchant or booking.cliente_id != request.user.pk):
            raise PermissionDenied("Somente o cliente pode aceitar o novo horário.")
        allowed = {"confirmar": {"solicitado"}, "propor": {"solicitado", "contraproposta"},
                   "aceitar_proposta": {"contraproposta"}, "recusar": {"solicitado", "contraproposta"},
                   "cancelar": {"solicitado", "contraproposta", "confirmado"}, "concluir": {"confirmado"}}
        if booking.status not in allowed[action_name]:
            raise ValidationError("Esta ação não está disponível no estado atual.")
        if action_name == "propor":
            if "inicio_proposto" not in values:
                raise ValidationError("Informe a nova data e o horário.")
            booking.inicio_proposto = validate_future(values["inicio_proposto"])
            booking.status = "contraproposta"
        elif action_name in {"confirmar", "aceitar_proposta"}:
            if not lojas_publicas().filter(pk=loja.pk).exists():
                raise ValidationError("Esta loja não está disponível para confirmar agendamentos.")
            start = validate_future(booking.inicio_solicitado if action_name == "confirmar" else booking.inicio_proposto)
            if Agendamento.objects.filter(loja=loja, status="confirmado", inicio_confirmado=start).exclude(pk=booking.pk).exists():
                raise ValidationError("A loja já tem um agendamento confirmado neste horário. Combine outro horário.")
            booking.inicio_confirmado = start
            booking.status = "confirmado"
        elif action_name == "concluir":
            if booking.inicio_confirmado > timezone.now():
                raise ValidationError("Aguarde o horário do serviço para concluir.")
            booking.status = "concluido"
        else:
            booking.status = "recusado" if action_name == "recusar" else "cancelado"
        if merchant and values["mensagem"].strip():
            booking.mensagem_loja = values["mensagem"]
        booking.versao += 1
        booking.save()
        return Response(BookingOutput(booking).data)
