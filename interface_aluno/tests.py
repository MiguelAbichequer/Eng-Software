"""
Testes da página "Minhas solicitações" e do cancelamento pelo aluno.

O "agora" é fixado (quarta-feira, 04/11/2026, 10:30) para o resultado não depender do relógio.
Para rodar:  python manage.py test interface_aluno
"""

from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno
from monitor.models import DiasSemana, Horario, Monitor, Solicitacao

#quarta-feira, 04/11/2026, 10:30
AGORA = timezone.make_aware(datetime(2026, 11, 4, 10, 30))
HOJE = AGORA.date()
QUARTA = DiasSemana.QUARTA.value


@patch('interface_aluno.views.agora_local', lambda: AGORA)
class MinhasSolicitacoesTests(TestCase):

    def setUp(self):
        self.ana = Aluno.objects.create(matricula='a1', nome='Ana')
        self.bruno = Aluno.objects.create(matricula='a2', nome='Bruno')
        self.monitor = Monitor.objects.create(matricula='m1', nome='Carla')
        #quarta 10:00-11:00 (acontecendo agora) e quarta 14:00-15:00 (mais tarde hoje)
        self.agora_h = Horario.objects.create(monitor=self.monitor, dia_semana=QUARTA, hora_inicio=time(10), hora_fim=time(11))
        self.tarde_h = Horario.objects.create(monitor=self.monitor, dia_semana=QUARTA, hora_inicio=time(14), hora_fim=time(15))

        sessao = self.client.session
        sessao['aluno_id'] = self.ana.id
        sessao.save()

    def pedido(self, horario, data=HOJE, aluno=None, assunto='Integrais'):
        return Solicitacao.objects.create(
            aluno=aluno or self.ana, horario=horario, data=data,
            assunto=assunto, formato='online', participantes='individual',
        )

    def pagina(self):
        return self.client.get(reverse('minhas_solicitacoes'))

    def url_cancelar(self, s):
        return reverse('cancelar_solicitacao', args=[s.id])

    # --- a página ---

    def test_exige_login(self):
        self.client.session.flush()
        self.client.cookies.clear()
        self.assertRedirects(self.pagina(), reverse('home'), fetch_redirect_response=False)

    def test_mostra_proximas_e_anteriores_separadas(self):
        self.pedido(self.tarde_h, assunto='Derivadas')
        self.pedido(self.agora_h, data=HOJE - timedelta(weeks=1), assunto='Limites')

        r = self.pagina()

        self.assertContains(r, 'Minhas solicitações</h1>', html=False)
        self.assertEqual([s.assunto for s in r.context['proximas']], ['Derivadas'])
        self.assertEqual([s.assunto for s in r.context['anteriores']], ['Limites'])
        self.assertContains(r, 'Derivadas')
        self.assertContains(r, 'Limites')
        self.assertContains(r, 'Carla')

    def test_futura_tem_botao_de_cancelar_apontando_para_ela(self):
        s = self.pedido(self.tarde_h)
        r = self.pagina()
        self.assertContains(r, f'action="{self.url_cancelar(s)}"')
        self.assertContains(r, 'Confirmar cancelamento')

    def test_em_andamento_aparece_mas_sem_botao_de_cancelar(self):
        s = self.pedido(self.agora_h)  #10:00-11:00, agora são 10:30
        r = self.pagina()
        self.assertContains(r, 'Acontecendo agora')
        self.assertContains(r, 'não dá mais para cancelar')
        self.assertNotContains(r, self.url_cancelar(s))

    def test_nao_mostra_solicitacoes_de_outro_aluno(self):
        self.pedido(self.tarde_h, aluno=self.bruno, assunto='Assunto do Bruno')
        r = self.pagina()
        self.assertNotContains(r, 'Assunto do Bruno')
        self.assertContains(r, 'Você não tem nenhum atendimento marcado')

    def test_sem_nada_mostra_os_avisos_de_vazio(self):
        r = self.pagina()
        self.assertContains(r, 'Você não tem nenhum atendimento marcado')
        self.assertContains(r, 'Nenhum atendimento realizado ainda')
        self.assertContains(r, f'href="{reverse("painel")}"')

    def test_anteriores_vem_das_mais_recentes_para_as_mais_antigas(self):
        self.pedido(self.agora_h, data=HOJE - timedelta(weeks=2), assunto='Antiga')
        self.pedido(self.agora_h, data=HOJE - timedelta(weeks=1), assunto='Recente')
        r = self.pagina()
        self.assertEqual([s.assunto for s in r.context['anteriores']], ['Recente', 'Antiga'])

    # --- o cancelamento a partir da página ---

    def test_cancelar_apaga_e_volta_para_a_pagina_com_aviso(self):
        s = self.pedido(self.tarde_h)

        r = self.client.post(self.url_cancelar(s), follow=True)

        self.assertRedirects(r, reverse('minhas_solicitacoes'))
        self.assertFalse(Solicitacao.objects.filter(pk=s.pk).exists())
        self.assertContains(r, 'Solicitação cancelada')
        self.assertContains(r, 'Você não tem nenhum atendimento marcado')

    def test_nao_cancela_o_que_ja_comecou(self):
        s = self.pedido(self.agora_h)
        r = self.client.post(self.url_cancelar(s), follow=True)
        self.assertTrue(Solicitacao.objects.filter(pk=s.pk).exists())
        self.assertContains(r, 'não pode mais ser cancelada')

    def test_nao_cancela_solicitacao_de_outro_aluno(self):
        s = self.pedido(self.tarde_h, aluno=self.bruno)
        self.assertEqual(self.client.post(self.url_cancelar(s)).status_code, 404)
        self.assertTrue(Solicitacao.objects.filter(pk=s.pk).exists())

    def test_cancelar_exige_post(self):
        s = self.pedido(self.tarde_h)
        self.assertEqual(self.client.get(self.url_cancelar(s)).status_code, 405)
        self.assertTrue(Solicitacao.objects.filter(pk=s.pk).exists())
