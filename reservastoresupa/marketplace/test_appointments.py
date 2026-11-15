import uuid
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from reservastoresupa.lojas.models import Loja, Categoria, Produto
from .models import Endereco, Agendamento


class AppointmentTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.customer = User.objects.create_user(username="booking-client")
        self.other = User.objects.create_user(username="booking-other")
        self.owner = User.objects.create_user(username="booking-owner")
        self.shop = Loja.objects.create(dono=self.owner, nome="Limpeza", modalidade_catalogo="servicos", ativa=True, assinatura_status="ativa", aberta=False)
        self.category = Categoria.objects.create(loja=self.shop, nome="Estofados")
        self.service = Produto.objects.create(loja=self.shop, categoria=self.category, nome="Sofá", preco="100")
        self.address = Endereco.objects.create(cliente=self.customer, condominio="Ébano", bloco="1", apartamento="4", destinatario="Cliente", telefone="81999990000")
        self.start = (timezone.now() + timedelta(days=2)).replace(second=0, microsecond=0)
        self.client.force_authenticate(self.customer)

    def request_booking(self, **override):
        values = {"servico": self.service.pk, "endereco": self.address.pk, "inicio_solicitado": self.start.isoformat(), "chave": str(uuid.uuid4())}
        values.update(override)
        return self.client.post("/api/agendamentos/", values, format="json")

    def answer(self, booking, user, action, **kwargs):
        self.client.force_authenticate(user)
        return self.client.post(f"/api/agendamentos/{booking['id']}/responder/", {"versao": booking["versao"], "acao": action, **kwargs}, format="json")

    def test_service_booking_works_while_store_is_closed_and_has_snapshots(self):
        response = self.request_booking()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "solicitado")
        self.address.apartamento = "99"
        self.address.save()
        self.assertEqual(Agendamento.objects.get().endereco["apartamento"], "4")

    def test_merchant_counterproposal_requires_customer_acceptance(self):
        booking = self.request_booking().data
        proposed = self.answer(booking, self.owner, "propor", inicio_proposto=(self.start + timedelta(hours=2)).isoformat(), mensagem="Posso atender às 16h.")
        self.assertEqual(proposed.status_code, 200)
        self.assertEqual(proposed.data["status"], "contraproposta")
        self.assertIsNone(proposed.data["inicio_confirmado"])
        self.assertEqual(self.answer(proposed.data, self.owner, "aceitar_proposta").status_code, 403)
        accepted = self.answer(proposed.data, self.customer, "aceitar_proposta")
        self.assertEqual(accepted.data["status"], "confirmado")
        self.assertEqual(accepted.data["inicio_confirmado"], accepted.data["inicio_proposto"])

    def test_customer_cannot_confirm_and_other_users_cannot_view_or_change(self):
        booking = self.request_booking().data
        self.assertEqual(self.answer(booking, self.customer, "confirmar").status_code, 403)
        self.assertEqual(self.answer(booking, self.other, "cancelar").status_code, 404)
        self.assertEqual(self.client.get("/api/agendamentos/").data, [])

    def test_retries_do_not_duplicate_requests(self):
        key = str(uuid.uuid4())
        first = self.request_booking(chave=key)
        again = self.request_booking(chave=key)
        self.assertEqual(first.data["id"], again.data["id"])
        self.assertEqual(Agendamento.objects.count(), 1)

    def test_duplicate_confirmed_time_and_stale_responses_are_rejected(self):
        first = self.request_booking().data
        second = self.request_booking().data
        self.assertEqual(self.answer(first, self.owner, "confirmar").status_code, 200)
        self.assertEqual(self.answer(second, self.owner, "confirmar").status_code, 400)
        self.assertEqual(self.answer(first, self.customer, "cancelar").status_code, 400)

    def test_future_date_and_owned_address_required_and_products_rejected(self):
        self.assertEqual(self.request_booking(inicio_solicitado=(timezone.now()-timedelta(days=1)).isoformat()).status_code, 400)
        other_address = Endereco.objects.create(cliente=self.other, condominio="Acácia", bloco="1", apartamento="1", destinatario="Other", telefone="81988887777")
        self.assertEqual(self.request_booking(endereco=other_address.pk).status_code, 404)
        self.shop.modalidade_catalogo = "produtos"
        self.shop.save()
        self.assertEqual(self.request_booking().status_code, 400)

    def test_status_filters_and_cancellation(self):
        booking = self.request_booking().data
        confirmed = self.answer(booking, self.owner, "confirmar").data
        self.assertEqual(len(self.client.get("/api/agendamentos/?status=confirmado").data), 1)
        self.assertEqual(self.client.get("/api/agendamentos/?status=pendentes").data, [])
        self.assertEqual(self.answer(confirmed, self.customer, "cancelar").data["status"], "cancelado")
        self.assertEqual(len(self.client.get("/api/agendamentos/?status=historico").data), 1)

    def test_decline_and_complete_only_after_service_time(self):
        booking = self.request_booking().data
        self.assertEqual(self.answer(booking, self.owner, "recusar").data["status"], "recusado")
        self.client.force_authenticate(self.customer)
        booked = self.request_booking().data
        confirmed = self.answer(booked, self.owner, "confirmar").data
        self.assertEqual(self.answer(confirmed, self.owner, "concluir").status_code, 400)
        Agendamento.objects.filter(pk=booked["id"]).update(inicio_confirmado=timezone.now()-timedelta(hours=2))
        self.assertEqual(self.answer(confirmed, self.owner, "concluir").data["status"], "concluido")
