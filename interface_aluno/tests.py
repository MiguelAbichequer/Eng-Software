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


@patch('interface_aluno.views.agora_local', lambda: AGORA)
class VariosAlunosNoMesmoHorarioTests(TestCase):
    """A monitoria é aberta: vários alunos podem reservar o mesmo horário na mesma data."""

    def setUp(self):
        self.ana = Aluno.objects.create(matricula='a1', nome='Ana')
        self.bruno = Aluno.objects.create(matricula='a2', nome='Bruno')
        self.monitor = Monitor.objects.create(matricula='m1', nome='Carla')
        #quarta 10:00-11:00 (acontecendo agora) e quarta 14:00-15:00 (mais tarde hoje)
        self.agora_h = Horario.objects.create(monitor=self.monitor, dia_semana=QUARTA, hora_inicio=time(10), hora_fim=time(11))
        self.tarde_h = Horario.objects.create(monitor=self.monitor, dia_semana=QUARTA, hora_inicio=time(14), hora_fim=time(15))

    def logar(self, aluno):
        sessao = self.client.session
        sessao['aluno_id'] = aluno.id
        sessao.save()

    def solicitar(self, horario, data=HOJE):
        return self.client.post(reverse('solicitar_horario', args=[horario.id]), {
            'data': data.isoformat(), 'assunto': 'Integrais',
            'formato': 'presencial', 'participantes': 'individual',
        }, follow=True)

    def pagina_do_monitor(self):
        return self.client.get(reverse('monitor_detalhe', args=[self.monitor.id]))

    def vaga(self, resposta, horario, data=HOJE):
        return next(v for v in resposta.context['vagas'] if v.horario == horario and v.data == data)

    def test_dois_alunos_reservam_o_mesmo_horario(self):
        self.logar(self.ana)
        self.solicitar(self.tarde_h)
        self.logar(self.bruno)
        r = self.solicitar(self.tarde_h)

        self.assertContains(r, 'Horário solicitado')
        alunos = set(Solicitacao.objects.filter(horario=self.tarde_h, data=HOJE).values_list('aluno__nome', flat=True))
        self.assertEqual(alunos, {'Ana', 'Bruno'})

    def test_o_mesmo_aluno_nao_reserva_duas_vezes(self):
        self.logar(self.ana)
        self.solicitar(self.tarde_h)
        r = self.solicitar(self.tarde_h)

        self.assertContains(r, 'Você já solicitou esse horário nessa data')
        self.assertEqual(Solicitacao.objects.count(), 1)

    def test_o_banco_tambem_impede_o_mesmo_aluno_duas_vezes(self):
        from django.db import IntegrityError, transaction
        dados = dict(aluno=self.ana, horario=self.tarde_h, data=HOJE, assunto='x', formato='online', participantes='individual')
        Solicitacao.objects.create(**dados)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Solicitacao.objects.create(**dados)

    def test_horario_reservado_continua_aparecendo_com_a_contagem(self):
        self.logar(self.ana)
        self.solicitar(self.tarde_h)

        #para a Ana: a vaga aparece como dela, sem formulário
        r = self.pagina_do_monitor()
        vaga = self.vaga(r, self.tarde_h)
        self.assertTrue(vaga.minha)
        self.assertEqual(vaga.inscritos, 1)
        self.assertContains(r, 'Você já reservou')

        #para o Bruno: a mesma vaga, com o aviso de quantos já reservaram e o formulário
        self.logar(self.bruno)
        r = self.pagina_do_monitor()
        vaga = self.vaga(r, self.tarde_h)
        self.assertFalse(vaga.minha)
        self.assertContains(r, '1 aluno já reservou')
        self.assertNotContains(r, 'Você já reservou')

    def test_em_atendimento_outro_aluno_ainda_pode_entrar_no_horario_de_agora(self):
        self.logar(self.ana)
        self.solicitar(self.agora_h)

        self.logar(self.bruno)
        r = self.pagina_do_monitor()
        self.assertEqual(r.context['resumo'].estado, 'em_atendimento')
        self.assertEqual(r.context['resumo'].inscritos_atual, 1)
        self.assertContains(r, 'Você ainda pode entrar neste horário')

        r = self.solicitar(self.agora_h)
        self.assertContains(r, 'Horário solicitado')
        self.assertEqual(Solicitacao.objects.filter(horario=self.agora_h).count(), 2)

    def test_cancelar_tira_so_o_proprio_aluno(self):
        self.logar(self.ana)
        self.solicitar(self.tarde_h)
        self.logar(self.bruno)
        self.solicitar(self.tarde_h)

        do_bruno = Solicitacao.objects.get(aluno=self.bruno)
        self.client.post(reverse('cancelar_solicitacao', args=[do_bruno.id]))

        self.assertEqual(list(Solicitacao.objects.values_list('aluno__nome', flat=True)), ['Ana'])
