from datetime import timedelta, datetime, time
from zoneinfo import ZoneInfo
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
from .models import Agendamento, Endereco, FotoAgendamento
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
        fields = ["id", "loja", "loja_nome", "cliente_nome", "servico", "servico_nome", "valor_referencia", "endereco", "inicio_solicitado", "inicio_proposto", "inicio_confirmado", "observacoes", "mensagem_loja", "status", "versao", "criado_em", "duracao_minutos", "duracao_proposta", "inicio_reagendamento", "reagendamento_origem", "motivo_reagendamento", "motivo_cancelamento", "fotos"]

    fotos = serializers.SerializerMethodField()

    def get_fotos(self, obj):
        return [photo.pk for photo in obj.fotos.all()]


class BookingInput(StrictSerializer):
    servico = serializers.IntegerField(min_value=1)
    endereco = serializers.IntegerField(min_value=1)
    inicio_solicitado = serializers.DateTimeField()
    observacoes = serializers.CharField(max_length=5000, allow_blank=True, default="")
    chave = serializers.UUIDField()

    def validate_inicio_solicitado(self, value):
        return validate_future(value)


class BookingAction(StrictSerializer):
    acao = serializers.ChoiceField(choices=["confirmar", "propor", "aceitar_proposta", "recusar", "cancelar", "concluir", "iniciar", "reagendar", "recusar_reagendamento"])
    versao = serializers.IntegerField(min_value=1)
    inicio_proposto = serializers.DateTimeField(required=False)
    mensagem = serializers.CharField(max_length=1000, allow_blank=True, default="")
    duracao_minutos = serializers.IntegerField(min_value=15, max_value=720, required=False)


class BookingEdit(StrictSerializer):
    versao = serializers.IntegerField(min_value=1)
    observacoes = serializers.CharField(max_length=5000, allow_blank=True)
    endereco = serializers.IntegerField(min_value=1, required=False)


class AgendamentoViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = BookingOutput
    pagination_class = OptionalPageNumberPagination

    def get_queryset(self):
        user = self.request.user
        qs = Agendamento.objects.filter(Q(cliente=user) | Q(loja__dono=user)).select_related("loja", "cliente").prefetch_related("fotos")
        state = self.request.query_params.get("status")
        if self.action == "list":
            if state == "pendentes":
                qs = qs.filter(Q(status__in=["solicitado", "contraproposta"]) | Q(status="confirmado", inicio_reagendamento__isnull=False))
            elif state == "historico":
                qs = qs.filter(status__in=["concluido", "recusado", "cancelado"])
            elif state == "confirmado":
                qs = qs.filter(status__in=["confirmado", "em_execucao"]).order_by("inicio_confirmado", "pk")
            query = self.request.query_params.get("busca", "")[:100].strip()
            if query:
                qs = qs.filter(Q(servico_nome__icontains=query) | Q(cliente__first_name__icontains=query) | Q(endereco__telefone__icontains=query) | Q(endereco__condominio__icontains=query))
        return qs

    @action(detail=False, methods=["get"])
    def resumo(self, request):
        qs = self.get_queryset()
        return Response({"total": qs.count(), "pendentes": qs.filter(Q(status__in=["solicitado", "contraproposta"]) | Q(status="confirmado", inicio_reagendamento__isnull=False)).count(), "agendados": qs.filter(status__in=["confirmado", "em_execucao"]).count(), "concluidos": qs.filter(status="concluido").count()})

    @action(detail=False, methods=["get"])
    def agenda(self, request):
        try:
            start = datetime.strptime(request.query_params["de"], "%Y-%m-%d").replace(tzinfo=ZoneInfo("America/Recife"))
            end = datetime.strptime(request.query_params["ate"], "%Y-%m-%d").replace(tzinfo=ZoneInfo("America/Recife")) + timedelta(days=1)
            if not timedelta(0) < end-start <= timedelta(days=7):
                raise ValueError()
        except (KeyError, ValueError):
            raise ValidationError("Selecione um período de até 7 dias.")
        rows = list(self.get_queryset().filter(status__in=["confirmado", "em_execucao"], inicio_confirmado__gte=start-timedelta(hours=12), inicio_confirmado__lt=end).order_by("inicio_confirmado", "pk")[:1001])
        if len(rows) > 1000:
            raise ValidationError("Há muitos atendimentos. Selecione um período menor.")
        return Response(BookingOutput([b for b in rows if b.inicio_confirmado + timedelta(minutes=b.duracao_minutos) > start], many=True).data)

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
        booking = Agendamento.objects.select_for_update(of=("self",)).select_related("loja", "cliente").get(pk=initial.pk)
        data = BookingAction(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        if values["versao"] != booking.versao:
            raise ValidationError("Este agendamento mudou. Atualize antes de responder.")
        merchant = loja.dono_id == request.user.pk
        action_name = values["acao"]
        if action_name in {"confirmar", "propor", "recusar", "concluir", "iniciar"} and not merchant:
            raise PermissionDenied("Somente a loja pode realizar esta ação.")
        if action_name == "aceitar_proposta" and (merchant or booking.cliente_id != request.user.pk):
            raise PermissionDenied("Somente o cliente pode aceitar o novo horário.")
        allowed = {"confirmar": {"solicitado", "confirmado"}, "propor": {"solicitado", "contraproposta", "confirmado"},
                   "aceitar_proposta": {"contraproposta", "confirmado"}, "recusar": {"solicitado", "contraproposta"},
                   "cancelar": {"solicitado", "contraproposta", "confirmado"}, "concluir": {"confirmado", "em_execucao"},
                   "iniciar": {"confirmado"}, "reagendar": {"solicitado", "contraproposta", "confirmado"}, "recusar_reagendamento": {"confirmado"}}
        if booking.status not in allowed[action_name]:
            raise ValidationError("Esta ação não está disponível no estado atual.")
        if action_name == "propor":
            if "inicio_proposto" not in values:
                raise ValidationError("Informe a nova data e o horário.")
            start = validate_future(values["inicio_proposto"])
            booking.duracao_proposta = values.get("duracao_minutos", booking.duracao_minutos)
            if booking.status == "confirmado":
                booking.inicio_reagendamento = start
                booking.reagendamento_origem = "loja"
                booking.motivo_reagendamento = values["mensagem"]
            else:
                booking.inicio_proposto = start
                booking.status = "contraproposta"
        elif action_name in {"confirmar", "aceitar_proposta"}:
            if not lojas_publicas().filter(pk=loja.pk).exists():
                raise ValidationError("Esta loja não está disponível para confirmar agendamentos.")
            if booking.status == "confirmado":
                expected = "cliente" if action_name == "confirmar" else "loja"
                if not booking.inicio_reagendamento or booking.reagendamento_origem != expected:
                    raise ValidationError("Não há uma proposta aguardando esta confirmação.")
                start = validate_future(booking.inicio_reagendamento)
            else:
                start = validate_future(booking.inicio_solicitado if action_name == "confirmar" else booking.inicio_proposto)
            duration = values.get("duracao_minutos", booking.duracao_minutos) if merchant else booking.duracao_proposta
            end = start + timedelta(minutes=duration)
            occupied = Agendamento.objects.filter(loja=loja, status__in=["confirmado", "em_execucao"], inicio_confirmado__lt=end).exclude(pk=booking.pk)
            if any(b.inicio_confirmado + timedelta(minutes=b.duracao_minutos) > start for b in occupied):
                raise ValidationError("Este período se sobrepõe a outro atendimento. Reserve também o tempo de deslocamento e escolha outro horário.")
            booking.inicio_confirmado = start
            booking.duracao_minutos = duration
            booking.status = "confirmado"
            booking.inicio_reagendamento = None
            booking.reagendamento_origem = ""
        elif action_name == "reagendar":
            if merchant:
                raise PermissionDenied("A loja deve usar Propor outro horário.")
            if "inicio_proposto" not in values:
                raise ValidationError("Informe a nova preferência de data e horário.")
            start = validate_future(values["inicio_proposto"])
            booking.motivo_reagendamento = values["mensagem"]
            if booking.status == "confirmado":
                booking.inicio_reagendamento = start
                booking.reagendamento_origem = "cliente"
            else:
                booking.inicio_solicitado = start
                booking.inicio_proposto = None
                booking.status = "solicitado"
        elif action_name == "recusar_reagendamento":
            if not booking.inicio_reagendamento or booking.reagendamento_origem == ("loja" if merchant else "cliente"):
                raise ValidationError("Não há uma proposta da outra parte para recusar.")
            booking.inicio_reagendamento = None
            booking.reagendamento_origem = ""
        elif action_name == "iniciar":
            if booking.inicio_confirmado > timezone.now():
                raise ValidationError("Aguarde o horário confirmado para iniciar.")
            booking.status = "em_execucao"
        elif action_name == "concluir":
            if booking.inicio_confirmado > timezone.now():
                raise ValidationError("Aguarde o horário do serviço para concluir.")
            booking.status = "concluido"
        else:
            booking.status = "recusado" if action_name == "recusar" else "cancelado"
            if action_name == "cancelar":
                booking.motivo_cancelamento = values["mensagem"]
        if merchant and values["mensagem"].strip():
            booking.mensagem_loja = values["mensagem"]
        booking.versao += 1
        booking.save()
        return Response(BookingOutput(booking).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def editar(self, request, pk=None):
        initial = get_object_or_404(self.get_queryset(), pk=pk)
        booking = Agendamento.objects.select_for_update().get(pk=initial.pk)
        if request.user.pk != booking.cliente_id:
            raise PermissionDenied("Somente o cliente pode editar a solicitação.")
        if booking.status not in {"solicitado", "contraproposta", "confirmado"}:
            raise ValidationError("Não é possível editar esta solicitação nesta etapa.")
        data = BookingEdit(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        if values["versao"] != booking.versao:
            raise ValidationError("Esta solicitação mudou. Atualize antes de editar.")
        booking.observacoes = values["observacoes"]
        if "endereco" in values:
            address = get_object_or_404(Endereco, pk=values["endereco"], cliente=request.user)
            if not all(getattr(address, f).strip() for f in ("condominio", "bloco", "apartamento", "destinatario", "telefone")):
                raise ValidationError("Complete o endereço antes de salvar.")
            booking.endereco = {f: getattr(address, f) for f in ("condominio", "bloco", "apartamento", "destinatario", "telefone", "complemento")}
        booking.versao += 1
        booking.save()
        return Response(BookingOutput(booking).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def fotos(self, request, pk=None):
        from .appointment_media import PhotoInput
        initial = get_object_or_404(self.get_queryset(), pk=pk)
        booking = Agendamento.objects.select_for_update().get(pk=initial.pk)
        if request.user.pk != booking.cliente_id:
            raise PermissionDenied("Somente o cliente pode adicionar fotos do estofado.")
        if booking.status not in {"solicitado", "contraproposta", "confirmado"}:
            raise ValidationError("Não é possível adicionar fotos nesta etapa.")
        data = PhotoInput(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        if booking.fotos.filter(chave=values["chave"]).exists():
            return Response(BookingOutput(booking).data)
        if booking.fotos.count() >= 5:
            raise ValidationError("Cada solicitação pode ter até 5 fotos.")
        if FotoAgendamento.objects.filter(chave=values["chave"]).exists():
            raise ValidationError("Esta foto já foi enviada em outra solicitação.")
        FotoAgendamento.objects.create(agendamento=booking, **values)
        booking.versao += 1
        booking.save(update_fields=["versao", "atualizado_em"])
        return Response(BookingOutput(booking).data, status=201)

    @action(detail=True, methods=["get"])
    def foto(self, request, pk=None):
        from .appointment_media import preview
        booking = self.get_object()
        try:
            photo_id = int(request.query_params.get("foto", ""))
        except ValueError:
            raise ValidationError("Informe uma foto válida.")
        photo = get_object_or_404(FotoAgendamento, agendamento=booking, pk=photo_id)
        return Response({"data_uri": preview(photo)}, headers={"Cache-Control": "private, no-store"})
