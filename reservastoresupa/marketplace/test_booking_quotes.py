from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from . import test_appointments as booking_tests
from .models import Agendamento

class BookingQuoteTests(APITestCase):
    setUp = booking_tests.AppointmentTests.setUp
    request_booking = booking_tests.AppointmentTests.request_booking
    answer = booking_tests.AppointmentTests.answer

    def quote(self, booking, user, action='enviar', **extra):
        self.client.force_authenticate(user)
        return self.client.post(f"/api/agendamentos/{booking['id']}/orcamento/", {'versao': booking['versao'], 'acao': action, **extra}, format='json')

    def test_owner_quote_customer_accept_and_price_is_locked(self):
        booking = self.request_booking().data
        offer = self.quote(booking, self.owner, valor='250.50', descricao='Sofá e duas cadeiras')
        self.assertEqual(offer.status_code, 200)
        self.assertEqual(offer.data['orcamento_valor'], '250.50')
        self.assertEqual(offer.data['status'], 'solicitado')
        accepted = self.quote(offer.data, self.customer, 'aceitar')
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.data['orcamento_status'], 'aceito')
        self.assertIsNotNone(accepted.data['orcamento_respondido_em'])
        self.assertEqual(accepted.data['status'], 'solicitado')
        self.assertEqual(self.quote(accepted.data,self.owner,valor='500').status_code,400)
        self.assertEqual(self.quote(accepted.data,self.customer,'recusar').status_code,400)

    def test_scoped_roles_and_tampered_client_value(self):
        booking = self.request_booking().data
        self.assertEqual(self.quote(booking,self.other,valor='200').status_code,404)
        self.assertEqual(self.quote(booking,self.customer,valor='200').status_code,403)
        offer=self.quote(booking,self.owner,valor='200').data
        self.assertEqual(self.quote(offer,self.owner,'aceitar').status_code,403)
        self.assertEqual(self.quote(offer,self.customer,'aceitar',valor='0.01').status_code,400)
        self.assertEqual(self.quote(offer,self.customer,'aceitar',orcamento_status='aceito').status_code,400)
        self.assertEqual(Agendamento.objects.get(pk=booking['id']).orcamento_status,'pendente')

    def test_refusal_allows_new_proposal_and_stale_accept_is_rejected(self):
        booking=self.request_booking().data
        offer=self.quote(booking,self.owner,valor='200').data
        refused=self.quote(offer,self.customer,'recusar').data
        self.assertEqual(refused['orcamento_status'],'recusado')
        revised=self.quote(refused,self.owner,valor='180').data
        self.assertEqual(revised['orcamento_status'],'pendente')
        self.assertIsNone(revised['orcamento_respondido_em'])
        self.assertEqual(self.quote(offer,self.customer,'aceitar').status_code,400)
        self.assertEqual(self.quote(revised,self.customer,'aceitar').data['orcamento_valor'],'180.00')

    def test_invalid_amounts_and_terminal_booking(self):
        booking=self.request_booking().data
        for value in ['0','-1','NaN','Infinity','1.234','100000000.00']:
            self.assertEqual(self.quote(booking,self.owner,valor=value).status_code,400,value)
        self.assertEqual(self.quote(booking,self.owner).status_code,400)
        ended=self.answer(booking,self.customer,'cancelar',mensagem='Teste').data
        self.assertEqual(self.quote(ended,self.owner,valor='100').status_code,400)

    def test_confirmed_quote_is_pending_and_service_waits_for_approval(self):
        confirmed=self.answer(self.request_booking().data,self.owner,'confirmar').data
        offer=self.quote(confirmed,self.owner,valor='100').data
        self.client.force_authenticate(self.customer)
        ids=[b['id'] for b in self.client.get('/api/agendamentos/?status=pendentes').data]
        self.assertIn(offer['id'],ids)
        self.assertEqual(self.client.get('/api/agendamentos/resumo/').data['pendentes'],1)
        Agendamento.objects.filter(pk=offer['id']).update(inicio_confirmado=timezone.now())
        self.assertEqual(self.answer(offer,self.owner,'iniciar').status_code,400)
        accepted=self.quote(offer,self.customer,'aceitar').data
        self.assertEqual(self.answer(accepted,self.owner,'iniciar').data['status'],'em_execucao')

    def test_quote_scope_cannot_be_edited_without_agreement(self):
        offer=self.quote(self.request_booking().data,self.owner,valor='100').data
        self.client.force_authenticate(self.customer)
        response=self.client.post(f"/api/agendamentos/{offer['id']}/editar/",{'versao':offer['versao'],'observacoes':'Mudar para dez sofás'},format='json')
        self.assertEqual(response.status_code,400)
