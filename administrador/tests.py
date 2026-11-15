"""
Testes da área do administrador: consultar e expulsar usuários.

O "agora" é fixado (quarta-feira, 04/11/2026, 10:30) para o resultado não depender do relógio.
Para rodar:  python manage.py test administrador
"""

from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno
from monitor.models import Disciplina, DiasSemana, Horario, Monitor, Solicitacao

#quarta-feira, 04/11/2026, 10:30
AGORA = timezone.make_aware(datetime(2026, 11, 4, 10, 30))
HOJE = AGORA.date()
QUARTA = DiasSemana.QUARTA.value

#o hash é lento de propósito, então é calculado uma vez só
HASH = make_password('segredo')


class BaseTeste(TestCase):
    def setUp(self):
        #o relógio é congelado em todos os lugares que decidem o que é "futuro"
        for alvo in ('administrador.views.agora_local', 'interface_aluno.views.agora_local',
                     'interface_monitor.views.agora_local'):
            patcher = patch(alvo, return_value=AGORA)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.admin = User.objects.create_user('admin', password='x', is_staff=True)
        self.aluno = Aluno.objects.create(matricula='a1', nome='Ana', senha=HASH)
        self.outro_aluno = Aluno.objects.create(matricula='a2', nome='Bruno', senha=HASH)
        self.monitor = Monitor.objects.create(matricula='m1', nome='Carla', senha=HASH)
        self.calculo = Disciplina.objects.create(codigo='MAT1', nome='Cálculo')
        self.monitor.disciplinas.add(self.calculo)

        #quarta 10:00-11:00 (acontecendo agora) e quarta 14:00-15:00 (mais tarde hoje)
        self.agora_h = Horario.objects.create(monitor=self.monitor, dia_semana=QUARTA, hora_inicio=time(10), hora_fim=time(11))
        self.tarde_h = Horario.objects.create(monitor=self.monitor, dia_semana=QUARTA, hora_inicio=time(14), hora_fim=time(15))

    def entrar_admin(self):
        self.client.force_login(self.admin)

    def pedido(self, horario, data=HOJE, aluno=None, assunto='Integrais', inicio=None, fim=None):
        #sem início/fim, a reserva ocupa o horário inteiro
        return Solicitacao.objects.create(
            aluno=aluno or self.aluno, horario=horario, data=data,
            hora_inicio=inicio or horario.hora_inicio, hora_fim=fim or horario.hora_fim,
            assunto=assunto, formato='online', participantes='individual',
        )

    def url(self, nome, tipo, usuario):
        return reverse(nome, args=[tipo, usuario.id])

    def expulsar(self, tipo, usuario, motivo='Faltou sem avisar'):
        return self.client.post(self.url('usuario_expulsar', tipo, usuario), {'motivo': motivo, 'confirmo': 'sim'})


class AcessoTests(BaseTeste):
    def test_sem_login_do_admin_vai_para_o_login_do_admin(self):
        for url in [reverse('usuarios'), self.url('usuario', 'aluno', self.aluno)]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302)
            self.assertIn(reverse('admin:login'), r['Location'])

    def test_aluno_logado_nao_acessa(self):
        sessao = self.client.session
        sessao['aluno_id'] = self.aluno.id
        sessao.save()
        r = self.client.get(reverse('usuarios'))
        self.assertIn(reverse('admin:login'), r['Location'])

    def test_usuario_do_django_sem_ser_equipe_nao_acessa(self):
        self.client.force_login(User.objects.create_user('comum', password='x'))
        r = self.client.get(reverse('usuarios'))
        self.assertIn(reverse('admin:login'), r['Location'])

    def test_sem_login_nao_expulsa(self):
        self.expulsar('aluno', self.aluno)
        self.aluno.refresh_from_db()
        self.assertFalse(self.aluno.expulso)

    def test_expulsar_e_readmitir_exigem_post(self):
        self.entrar_admin()
        for nome in ('usuario_expulsar', 'usuario_readmitir'):
            self.assertEqual(self.client.get(self.url(nome, 'aluno', self.aluno)).status_code, 405)

    def test_tipo_invalido_e_id_inexistente_dao_404(self):
        self.entrar_admin()
        self.assertEqual(self.client.get(reverse('usuario', args=['professor', self.aluno.id])).status_code, 404)
        self.assertEqual(self.client.get(reverse('usuario', args=['aluno', 999])).status_code, 404)


class ListaTests(BaseTeste):
    def setUp(self):
        super().setUp()
        self.entrar_admin()

    def nomes(self, **filtros):
        r = self.client.get(reverse('usuarios'), filtros)
        return [(l.usuario.nome, l.tipo) for l in r.context['linhas']]

    def test_lista_alunos_e_monitores_em_ordem_de_nome(self):
        self.assertEqual(self.nomes(), [('Ana', 'aluno'), ('Bruno', 'aluno'), ('Carla', 'monitor')])

    def test_busca_por_nome_ou_matricula_sem_diferenciar_maiusculas(self):
        self.assertEqual(self.nomes(busca='car'), [('Carla', 'monitor')])
        self.assertEqual(self.nomes(busca='A2'), [('Bruno', 'aluno')])

    def test_filtro_por_tipo_e_situacao(self):
        self.outro_aluno.expulso_em = AGORA
        self.outro_aluno.save()
        self.assertEqual(self.nomes(tipo='monitor'), [('Carla', 'monitor')])
        self.assertEqual(self.nomes(situacao='expulsos'), [('Bruno', 'aluno')])
        self.assertEqual(self.nomes(tipo='aluno', situacao='ativos'), [('Ana', 'aluno')])

    def test_filtros_invalidos_sao_ignorados(self):
        self.assertEqual(len(self.nomes(tipo='xyz', situacao='xyz')), 3)

    def test_conta_os_atendimentos_de_cada_um(self):
        self.pedido(self.agora_h)
        self.pedido(self.tarde_h, aluno=self.outro_aluno)
        r = self.client.get(reverse('usuarios'))
        totais = {l.usuario.nome: l.solicitacoes for l in r.context['linhas']}
        self.assertEqual(totais, {'Ana': 1, 'Bruno': 1, 'Carla': 2})

    def test_mesma_matricula_como_aluno_e_monitor_aparece_duas_vezes(self):
        Monitor.objects.create(matricula='a1', nome='Ana')
        self.assertEqual(self.nomes(busca='a1'), [('Ana', 'aluno'), ('Ana', 'monitor')])


class FichaTests(BaseTeste):
    def setUp(self):
        super().setUp()
        self.entrar_admin()

    def test_ficha_do_aluno_separa_proximos_e_historico(self):
        passado = self.pedido(self.agora_h, data=HOJE - timedelta(weeks=1), assunto='Limites')
        futuro = self.pedido(self.tarde_h, assunto='Derivadas')
        r = self.client.get(self.url('usuario', 'aluno', self.aluno))
        self.assertEqual(r.context['proximas'], [futuro])
        self.assertEqual(r.context['anteriores'], [passado])
        self.assertContains(r, 'Derivadas')
        self.assertContains(r, 'Limites')

    def test_ficha_do_monitor_mostra_disciplinas_horarios_e_situacao(self):
        r = self.client.get(self.url('usuario', 'monitor', self.monitor))
        self.assertContains(r, 'Cálculo')
        self.assertContains(r, 'Quarta-feira, 10:00')
        self.assertContains(r, 'Indisponível (escolhido pelo monitor)')

    def test_aviso_diz_quantos_atendimentos_serao_cancelados(self):
        self.pedido(self.tarde_h)
        r = self.client.get(self.url('usuario', 'aluno', self.aluno))
        self.assertEqual(r.context['a_cancelar'], 1)
        self.assertContains(r, '1 atendimento que ainda não começou será cancelado')


class ExpulsarTests(BaseTeste):
    def setUp(self):
        super().setUp()
        self.entrar_admin()

    def test_exige_motivo_e_confirmacao(self):
        r1 = self.client.post(self.url('usuario_expulsar', 'aluno', self.aluno), {'motivo': '  ', 'confirmo': 'sim'})
        r2 = self.client.post(self.url('usuario_expulsar', 'aluno', self.aluno), {'motivo': 'x' * 201, 'confirmo': 'sim'})
        r3 = self.client.post(self.url('usuario_expulsar', 'aluno', self.aluno), {'motivo': 'Faltas'})
        self.aluno.refresh_from_db()
        self.assertFalse(self.aluno.expulso)
        for r in (r1, r2, r3):
            self.assertRedirects(r, self.url('usuario', 'aluno', self.aluno))

    def test_expulsa_e_guarda_quando_e_por_que(self):
        self.expulsar('aluno', self.aluno, motivo='  Faltou   3 vezes ')
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.expulso_em, AGORA)
        self.assertEqual(self.aluno.motivo_expulsao, 'Faltou 3 vezes')

    def test_cancela_so_os_atendimentos_que_nao_comecaram(self):
        passado = self.pedido(self.agora_h, data=HOJE - timedelta(weeks=1))
        em_andamento = self.pedido(self.agora_h)  #10:00-11:00, agora são 10:30
        futuro = self.pedido(self.tarde_h)

        self.expulsar('aluno', self.aluno)

        restantes = set(Solicitacao.objects.values_list('pk', flat=True))
        self.assertEqual(restantes, {passado.pk, em_andamento.pk})
        self.assertNotIn(futuro.pk, restantes)

    def test_nao_mexe_nos_atendimentos_de_outras_pessoas(self):
        do_bruno = self.pedido(self.tarde_h, aluno=self.outro_aluno)
        self.expulsar('aluno', self.aluno)
        self.assertTrue(Solicitacao.objects.filter(pk=do_bruno.pk).exists())

    def test_expulsar_monitor_cancela_os_atendimentos_futuros_que_ele_recebeu_e_fica_indisponivel(self):
        self.pedido(self.tarde_h, aluno=self.aluno)
        self.pedido(self.tarde_h, data=HOJE + timedelta(weeks=1), aluno=self.outro_aluno)
        self.monitor.status = 'disponivel'
        self.monitor.save()

        self.expulsar('monitor', self.monitor)

        self.monitor.refresh_from_db()
        self.assertTrue(self.monitor.expulso)
        self.assertEqual(self.monitor.status, 'indisponivel')
        self.assertFalse(Solicitacao.objects.exists())

    def test_expulsar_de_novo_nao_muda_a_data(self):
        self.expulsar('aluno', self.aluno)
        primeira = Aluno.objects.get(pk=self.aluno.pk).expulso_em
        self.expulsar('aluno', self.aluno, motivo='Outro motivo')
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.expulso_em, primeira)
        self.assertEqual(self.aluno.motivo_expulsao, 'Faltou sem avisar')

    def test_readmitir_limpa_a_expulsao(self):
        self.expulsar('aluno', self.aluno)
        self.client.post(self.url('usuario_readmitir', 'aluno', self.aluno))
        self.aluno.refresh_from_db()
        self.assertFalse(self.aluno.expulso)
        self.assertEqual(self.aluno.motivo_expulsao, '')


class EfeitosDaExpulsaoTests(BaseTeste):
    """O que muda no resto do sistema depois que o administrador expulsa alguém."""

    def marcar_expulso(self, usuario):
        usuario.expulso_em = AGORA
        usuario.motivo_expulsao = 'Teste'
        usuario.save()

    def test_aluno_expulso_nao_consegue_entrar(self):
        self.marcar_expulso(self.aluno)
        r = self.client.post('/', {'tipo': 'aluno', 'username': 'a1', 'password': 'segredo'})
        self.assertContains(r, 'Esta conta foi suspensa')
        self.assertNotIn('aluno_id', self.client.session)

    def test_monitor_expulso_nao_consegue_entrar(self):
        self.marcar_expulso(self.monitor)
        r = self.client.post('/', {'tipo': 'monitor', 'username': 'm1', 'password': 'segredo'})
        self.assertContains(r, 'Esta conta foi suspensa')
        self.assertNotIn('monitor_id', self.client.session)

    def test_senha_errada_de_expulso_nao_revela_a_expulsao(self):
        self.marcar_expulso(self.aluno)
        r = self.client.post('/', {'tipo': 'aluno', 'username': 'a1', 'password': 'errada'})
        self.assertContains(r, 'Senha incorreta')
        self.assertNotContains(r, 'suspensa')

    def test_sessao_aberta_do_aluno_cai_na_proxima_tela(self):
        sessao = self.client.session
        sessao['aluno_id'] = self.aluno.id
        sessao.save()
        self.marcar_expulso(self.aluno)

        r = self.client.get(reverse('painel'))
        self.assertRedirects(r, reverse('home') + '?suspenso=1')
        self.assertNotIn('aluno_id', self.client.session)
        self.assertContains(self.client.get(r['Location']), 'Esta conta foi suspensa')

    def test_sessao_aberta_do_monitor_cai_na_proxima_tela(self):
        sessao = self.client.session
        sessao['monitor_id'] = self.monitor.id
        sessao.save()
        self.marcar_expulso(self.monitor)

        r = self.client.get(reverse('monitor_painel'))
        self.assertRedirects(r, reverse('home') + '?suspenso=1')
        self.assertNotIn('monitor_id', self.client.session)

    def test_monitor_expulso_some_para_os_alunos(self):
        sessao = self.client.session
        sessao['aluno_id'] = self.aluno.id
        sessao.save()
        self.marcar_expulso(self.monitor)

        painel = self.client.get(reverse('painel'))
        self.assertEqual(painel.context['resumos'], [])
        self.assertNotIn(self.calculo, list(painel.context['disciplinas']))
        self.assertEqual(self.client.get(reverse('monitor_detalhe', args=[self.monitor.id])).status_code, 404)

        r = self.client.post(reverse('solicitar_horario', args=[self.tarde_h.id]), {
            'data': HOJE.isoformat(), 'assunto': 'x', 'formato': 'online', 'participantes': 'individual',
        })
        self.assertEqual(r.status_code, 404)
        self.assertFalse(Solicitacao.objects.exists())

    def test_readmitido_volta_a_entrar(self):
        self.marcar_expulso(self.aluno)
        self.aluno.expulso_em = None
        self.aluno.save()
        r = self.client.post('/', {'tipo': 'aluno', 'username': 'a1', 'password': 'segredo'})
        self.assertRedirects(r, reverse('painel'), fetch_redirect_response=False)

    def test_historico_do_expulso_continua_no_relatorio(self):
        self.pedido(self.agora_h, data=HOJE - timedelta(days=1 + 6))  #quarta da semana passada
        self.marcar_expulso(self.aluno)
        self.entrar_admin()
        r = self.client.get(reverse('relatorio'), {'inicio': '2026-10-01', 'fim': '2026-11-30'})
        self.assertEqual(r.context['resumo']['total'], 1)
