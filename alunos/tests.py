"""
Testes da página "Minhas solicitações" e do cancelamento pelo aluno.

O "agora" é fixado (quarta-feira, 04/11/2026, 10:30) para o resultado não depender do relógio.
Para rodar:  python manage.py test alunos
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


@patch('alunos.views.agora_local', lambda: AGORA)
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

    def pedido(self, horario, data=HOJE, aluno=None, assunto='Integrais', inicio=None, fim=None):
        #sem início/fim, a reserva ocupa o horário inteiro
        return Solicitacao.objects.create(
            aluno=aluno or self.ana, horario=horario, data=data,
            hora_inicio=inicio or horario.hora_inicio, hora_fim=fim or horario.hora_fim,
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


@patch('alunos.views.agora_local', lambda: AGORA)
class BlocosTests(TestCase):
    """Reserva em blocos de 15 minutos: cada bloco é de um aluno só."""

    def setUp(self):
        self.ana = Aluno.objects.create(matricula='a1', nome='Ana')
        self.bruno = Aluno.objects.create(matricula='a2', nome='Bruno')
        self.monitor = Monitor.objects.create(matricula='m1', nome='Carla')
        self.outro_monitor = Monitor.objects.create(matricula='m2', nome='Diego')
        #quarta 10:00-11:00 (acontecendo agora, 10:30) e quarta 14:00-15:00 (mais tarde hoje)
        self.agora_h = Horario.objects.create(monitor=self.monitor, dia_semana=QUARTA, hora_inicio=time(10), hora_fim=time(11))
        self.tarde_h = Horario.objects.create(monitor=self.monitor, dia_semana=QUARTA, hora_inicio=time(14), hora_fim=time(15))
        self.logar(self.ana)

    def logar(self, aluno):
        sessao = self.client.session
        sessao['aluno_id'] = aluno.id
        sessao.save()

    def reservar(self, horario, *blocos, data=HOJE):
        return self.client.post(reverse('solicitar_horario', args=[horario.id]), {
            'data': data.isoformat(), 'blocos': list(blocos), 'assunto': 'Integrais',
            'formato': 'presencial', 'participantes': 'individual',
        }, follow=True)

    def trechos(self, aluno=None):
        qs = Solicitacao.objects.filter(aluno=aluno) if aluno else Solicitacao.objects.all()
        return [(f'{s.hora_inicio:%H:%M}', f'{s.hora_fim:%H:%M}') for s in qs.order_by('hora_inicio')]

    def situacoes(self, horario, data=HOJE):
        r = self.client.get(reverse('monitor_detalhe', args=[self.monitor.id]))
        vaga = next(v for v in r.context['vagas'] if v.horario == horario and v.data == data)
        return {f'{c.inicio:%H:%M}': c.situacao for c in vaga.blocos}

    # --- os blocos na tela ---

    def test_horario_vira_blocos_de_15_minutos(self):
        self.assertEqual(self.situacoes(self.tarde_h),
                         {'14:00': 'livre', '14:15': 'livre', '14:30': 'livre', '14:45': 'livre'})

    def test_blocos_que_ja_comecaram_nao_podem_ser_reservados(self):
        #agora são 10:30: 10:00, 10:15 e 10:30 já começaram
        self.assertEqual(self.situacoes(self.agora_h),
                         {'10:00': 'passou', '10:15': 'passou', '10:30': 'passou', '10:45': 'livre'})
        r = self.reservar(self.agora_h, '10:15')
        self.assertContains(r, 'não está mais livre')
        self.assertFalse(Solicitacao.objects.exists())

    def test_reservada_fica_sua_para_o_dono_e_cinza_para_os_outros(self):
        self.reservar(self.tarde_h, '14:15')
        self.assertEqual(self.situacoes(self.tarde_h)['14:15'], 'meu')
        self.logar(self.bruno)
        situacoes = self.situacoes(self.tarde_h)
        self.assertEqual(situacoes['14:15'], 'ocupado')
        self.assertEqual(situacoes['14:00'], 'livre')
        r = self.client.get(reverse('monitor_detalhe', args=[self.monitor.id]))
        self.assertContains(r, 'bloco bloco-ocupado')

    # --- reservar ---

    def test_blocos_seguidas_viram_uma_solicitacao(self):
        r = self.reservar(self.tarde_h, '14:00', '14:15', '14:30')
        self.assertContains(r, 'Horário solicitado')
        self.assertEqual(self.trechos(), [('14:00', '14:45')])

    def test_blocos_separadas_viram_solicitacoes_diferentes(self):
        self.reservar(self.tarde_h, '14:00', '14:15', '14:45')
        self.assertEqual(self.trechos(), [('14:00', '14:30'), ('14:45', '15:00')])

    def test_a_ordem_e_repeticoes_nao_importam(self):
        self.reservar(self.tarde_h, '14:15', '14:00', '14:15')
        self.assertEqual(self.trechos(), [('14:00', '14:30')])

    def test_dois_alunos_reservam_blocos_diferentes_do_mesmo_horario(self):
        self.reservar(self.tarde_h, '14:00')
        self.logar(self.bruno)
        r = self.reservar(self.tarde_h, '14:15')
        self.assertContains(r, 'Horário solicitado')
        self.assertEqual(self.trechos(self.ana), [('14:00', '14:15')])
        self.assertEqual(self.trechos(self.bruno), [('14:15', '14:30')])

    def test_bloco_de_outro_aluno_nao_pode_ser_reservado_e_nada_e_gravado(self):
        self.reservar(self.tarde_h, '14:15')
        self.logar(self.bruno)
        r = self.reservar(self.tarde_h, '14:00', '14:15')  #um livre e um ocupado
        self.assertContains(r, 'O horário das 14:15 não está mais livre')
        self.assertEqual(self.trechos(self.bruno), [])     #nem a livre foi gravada

    def test_sem_bloco_marcado(self):
        r = self.reservar(self.tarde_h)
        self.assertContains(r, 'Marque pelo menos um horário')
        self.assertFalse(Solicitacao.objects.exists())

    def test_bloco_fora_do_horario_ou_texto_invalido(self):
        r = self.reservar(self.tarde_h, '13:45')
        self.assertContains(r, 'não faz parte deste atendimento')
        r = self.reservar(self.tarde_h, 'abc')  #lixo é ignorado: fica sem bloco
        self.assertContains(r, 'Marque pelo menos um horário')
        self.assertFalse(Solicitacao.objects.exists())

    def test_data_fora_da_janela(self):
        r = self.reservar(self.tarde_h, '14:00', data=HOJE + timedelta(weeks=5))
        self.assertContains(r, 'não está mais disponível')

    # --- limite por dia ---

    def test_limite_de_4_blocos_por_dia_com_o_mesmo_monitor(self):
        self.reservar(self.tarde_h, '14:00', '14:15', '14:30')
        r = self.reservar(self.tarde_h, '14:45')
        self.assertContains(r, 'Horário solicitado')  #3 + 1 = 4: ainda cabe

        r = self.reservar(self.agora_h, '10:45')     #a 5ª, em outro horário do mesmo monitor e dia
        self.assertContains(r, 'até 4 horários de 15 minutos por dia com o mesmo monitor (60 minutos no total)')
        self.assertContains(r, 'Você ainda pode reservar 0 nesse dia')
        self.assertEqual(len(self.trechos()), 2)

    def test_limite_diz_quantas_ainda_cabem(self):
        self.reservar(self.tarde_h, '14:00', '14:15', '14:30')
        r = self.reservar(self.agora_h, '10:45')
        self.assertContains(r, 'Horário solicitado')
        Solicitacao.objects.filter(hora_inicio=time(10, 45)).delete()
        r = self.client.get(reverse('monitor_detalhe', args=[self.monitor.id]))
        self.assertContains(r, 'Você ainda pode marcar 1 neste dia')

    def test_limite_e_por_monitor_e_por_dia(self):
        self.reservar(self.tarde_h, '14:00', '14:15', '14:30', '14:45')
        #outro monitor no mesmo dia: conta separado
        h_diego = Horario.objects.create(monitor=self.outro_monitor, dia_semana=QUARTA, hora_inicio=time(16), hora_fim=time(17))
        self.assertContains(self.reservar(h_diego, '16:00'), 'Horário solicitado')
        #mesmo monitor, semana que vem: conta separado
        self.assertContains(self.reservar(self.tarde_h, '14:00', data=HOJE + timedelta(weeks=1)), 'Horário solicitado')

    # --- cancelar e regras do horário ---

    def test_cancelar_libera_as_blocos(self):
        self.reservar(self.tarde_h, '14:00', '14:15')
        s = Solicitacao.objects.get()
        self.client.post(reverse('cancelar_solicitacao', args=[s.id]))
        self.assertEqual(set(self.situacoes(self.tarde_h).values()), {'livre'})

    def test_horario_precisa_ser_multiplo_de_15_minutos(self):
        from django.core.exceptions import ValidationError
        h = Horario(monitor=self.monitor, dia_semana=QUARTA + 1, hora_inicio=time(14, 10), hora_fim=time(15))
        with self.assertRaises(ValidationError):
            h.full_clean()
        h.hora_inicio = time(14, 15)
        h.full_clean()  #múltiplo de 15: passa


class AgruparSeguidasTests(TestCase):
    """A função que junta blocos seguidos em trechos, testada sozinha."""

    def test_agrupa(self):
        from .reservas import agrupar_seguidas
        t = lambda texto: time.fromisoformat(texto)
        self.assertEqual(agrupar_seguidas([]), [])
        self.assertEqual(agrupar_seguidas([t('14:00')]), [(t('14:00'), t('14:15'))])
        self.assertEqual(
            agrupar_seguidas([t('14:00'), t('14:15'), t('15:00'), t('15:15'), t('15:45')]),
            [(t('14:00'), t('14:30')), (t('15:00'), t('15:30')), (t('15:45'), t('16:00'))],
        )
