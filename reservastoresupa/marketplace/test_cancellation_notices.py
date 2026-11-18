from rest_framework.test import APITestCase
from . import test_appointments as booking_tests
from .models import Agendamento

class CancellationNoticeTests(APITestCase):
    setUp = booking_tests.AppointmentTests.setUp
    request_booking = booking_tests.AppointmentTests.request_booking
    answer = booking_tests.AppointmentTests.answer

    def test_merchant_cancellation_notifies_customer_and_remains_in_all_and_history(self):
        original=self.request_booking().data
        cancelled=self.answer(original,self.owner,'cancelar',mensagem='Equipe indisponível').data
        self.assertEqual(cancelled['cancelado_por'],'loja')
        self.assertIsNotNone(cancelled['cancelado_em'])
        self.client.force_authenticate(self.customer)
        notices=self.client.get('/api/agendamentos/avisos/').data
        self.assertEqual([b['id'] for b in notices],[original['id']])
        self.assertEqual(notices[0]['motivo_cancelamento'],'Equipe indisponível')
        self.assertEqual(self.client.get('/api/agendamentos/?status=todos').data[0]['status'],'cancelado')
        self.assertEqual(self.client.get('/api/agendamentos/?status=historico').data[0]['status'],'cancelado')
        self.assertEqual(self.client.get('/api/agendamentos/?status=pendentes').data,[])

    def test_acknowledgment_is_scoped_idempotent_and_does_not_change_booking_version(self):
        cancelled=self.answer(self.request_booking().data,self.owner,'cancelar',mensagem='Teste').data
        path=f"/api/agendamentos/{cancelled['id']}/cancelamento-visto/"
        self.assertEqual(self.client.post(path,{},format='json').status_code,403)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/agendamentos/avisos/').data,[])
        self.assertEqual(self.client.post(path,{},format='json').status_code,404)
        self.client.force_authenticate(self.customer)
        self.assertEqual(self.client.post(path,{},format='json').status_code,200)
        self.assertEqual(self.client.post(path,{},format='json').status_code,200)
        self.assertEqual(self.client.get('/api/agendamentos/avisos/').data,[])
        self.assertEqual(Agendamento.objects.get(pk=cancelled['id']).versao,cancelled['versao'])

    def test_customer_cancellation_does_not_notify_same_customer(self):
        cancelled=self.answer(self.request_booking().data,self.customer,'cancelar',mensagem='Desisti').data
        self.assertEqual(cancelled['cancelado_por'],'cliente')
        self.assertEqual(self.client.get('/api/agendamentos/avisos/').data,[])

    def test_unacknowledged_legacy_cancellation_is_visible_but_not_misattributed(self):
        original=self.request_booking().data
        Agendamento.objects.filter(pk=original['id']).update(status='cancelado',motivo_cancelamento='Cancelado anteriormente')
        notices=self.client.get('/api/agendamentos/avisos/').data
        self.assertEqual(len(notices),1)
        self.assertEqual(notices[0]['cancelado_por'],'')
