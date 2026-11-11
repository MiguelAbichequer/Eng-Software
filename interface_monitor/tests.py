from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno
from monitor.admin import MonitorAdmin
from monitor.models import Disciplina, DiasSemana, Horario, Monitor, Solicitacao

#quarta-feira, 04/11/2026, 10:30
AGORA = timezone.make_aware(datetime(2026, 11, 4, 10, 30))
HOJE = AGORA.date()
QUARTA = DiasSemana.QUARTA.value

#o hash é lento de propósito, então é calculado uma vez só
HASH = make_password('segredo')


def fixar_agora(teste):
    """Congela o relógio das views do monitor em AGORA."""
    patcher = patch('interface_monitor.views.agora_local', return_value=AGORA)
    patcher.start()
    teste.addCleanup(patcher.stop)


class BaseTeste(TestCase):
    def setUp(self):
        fixar_agora(self)
        self.monitor = Monitor.objects.create(matricula='m1', nome='Breno', senha=HASH)
        self.outro = Monitor.objects.create(matricula='m2', nome='Carla', senha=HASH)
        self.aluno = Aluno.objects.create(matricula='a1', nome='Ana', senha=HASH)

    def entrar(self, monitor=None):
        sessao = self.client.session
        sessao['monitor_id'] = (monitor or self.monitor).id
        sessao.save()

    def horario(self, dia=QUARTA, inicio=time(10, 0), fim=time(11, 0), monitor=None):
        return Horario.objects.create(monitor=monitor or self.monitor, dia_semana=dia, hora_inicio=inicio, hora_fim=fim)

    def pedido(self, horario, data=HOJE, aluno=None, assunto='Integrais'):
        return Solicitacao.objects.create(
            aluno=aluno or self.aluno, horario=horario, data=data,
            assunto=assunto, formato='online', participantes='individual',
        )


class LoginTests(BaseTeste):
    def test_monitor_entra_e_vai_para_o_painel_dele(self):
        r = self.client.post('/', {'tipo': 'monitor', 'username': 'm1', 'password': 'segredo'})
        self.assertRedirects(r, reverse('monitor_painel'))
        self.assertEqual(self.client.session['monitor_id'], self.monitor.id)
        self.assertNotIn('aluno_id', self.client.session)

    def test_aluno_continua_entrando_como_antes(self):
        r = self.client.post('/', {'tipo': 'aluno', 'username': 'a1', 'password': 'segredo'})
        self.assertRedirects(r, reverse('painel'), fetch_redirect_response=False)
        self.assertEqual(self.client.session['aluno_id'], self.aluno.id)

    def test_sem_escolher_o_papel_entra_como_aluno(self):
        r = self.client.post('/', {'username': 'a1', 'password': 'segredo'})
        self.assertRedirects(r, reverse('painel'), fetch_redirect_response=False)

    def test_mesma_matricula_de_aluno_e_monitor_entra_no_papel_escolhido(self):
        Aluno.objects.create(matricula='m1', nome='Breno aluno', senha=make_password('outra'))
        r = self.client.post('/', {'tipo': 'monitor', 'username': 'm1', 'password': 'segredo'})
        self.assertRedirects(r, reverse('monitor_painel'))

    def test_senha_errada_e_matricula_inexistente(self):
        r = self.client.post('/', {'tipo': 'monitor', 'username': 'm1', 'password': 'errada'})
        self.assertContains(r, 'Senha incorreta.')
        self.assertContains(r, 'value="monitor" checked')  #mantém o papel escolhido
        r = self.client.post('/', {'tipo': 'monitor', 'username': 'zzz', 'password': 'x'})
        self.assertContains(r, 'Matrícula não encontrada.')

    def test_monitor_sem_senha_cadastrada_nao_entra(self):
        Monitor.objects.create(matricula='m3', nome='Sem senha')
        r = self.client.post('/', {'tipo': 'monitor', 'username': 'm3', 'password': ''})
        self.assertContains(r, 'Senha incorreta.')

    def test_quem_ja_esta_logado_vai_direto_para_a_sua_tela(self):
        self.entrar()
        self.assertRedirects(self.client.get('/'), reverse('monitor_painel'))

    def test_trocar_de_papel_nao_deixa_as_duas_sessoes_ativas(self):
        sessao = self.client.session
        sessao['aluno_id'] = self.aluno.id
        sessao.save()
        self.client.post('/', {'tipo': 'monitor', 'username': 'm1', 'password': 'segredo'})
        self.assertNotIn('aluno_id', self.client.session)

    def test_cadastro_do_monitor_guarda_senha_com_hash(self):
        self.client.post('/monitor/cadastro/', {'matricula': 'm9', 'nome': 'Novo', 'senha': 'abc123'})
        novo = Monitor.objects.get(matricula='m9')
        self.assertNotEqual(novo.senha, 'abc123')
        self.assertTrue(check_password('abc123', novo.senha))


class AcessoTests(BaseTeste):
    URLS = ['monitor_painel', 'monitor_horarios']

    def test_sem_login_volta_para_o_inicio(self):
        for nome in self.URLS:
            self.assertRedirects(self.client.get(reverse(nome)), reverse('home'), msg_prefix=nome)

    def test_aluno_logado_nao_acessa_a_area_do_monitor(self):
        sessao = self.client.session
        sessao['aluno_id'] = self.aluno.id
        sessao.save()
        for nome in self.URLS:
            r = self.client.get(reverse(nome))
            self.assertRedirects(r, reverse('home'), fetch_redirect_response=False, msg_prefix=nome)

    def test_monitor_apagado_depois_do_login_limpa_a_sessao(self):
        self.entrar()
        self.monitor.delete()
        self.assertRedirects(self.client.get(reverse('monitor_painel')), reverse('home'))
        self.assertNotIn('monitor_id', self.client.session)

    def test_acoes_exigem_post(self):
        self.entrar()
        h = self.horario()
        s = self.pedido(h, data=HOJE.replace(day=11))
        for url in [reverse('monitor_horario_novo'),
                    reverse('monitor_horario_remover', args=[h.id]),
                    reverse('monitor_atendimento_remover', args=[s.id])]:
            self.assertEqual(self.client.get(url).status_code, 405, url)


class PainelTests(BaseTeste):
    def test_horario_de_agora_sem_pedido_aparece_como_disponivel(self):
        self.horario()
        self.entrar()
        r = self.client.get(reverse('monitor_painel'))
        self.assertEqual(r.context['resumo'].estado, 'disponivel')
        self.assertContains(r, 'Disponível agora')
        self.assertContains(r, 'até 11:00')

    def test_horario_de_agora_com_pedido_mostra_quem_e_o_assunto(self):
        self.pedido(self.horario(), assunto='Séries de Taylor')
        self.entrar()
        r = self.client.get(reverse('monitor_painel'))
        self.assertEqual(r.context['resumo'].estado, 'em_atendimento')
        self.assertContains(r, 'Em atendimento')
        self.assertContains(r, 'Ana: Séries de Taylor')
        self.assertContains(r, 'Já começou')           #em andamento: não dá mais para remover
        self.assertNotContains(r, 'Confirmar remoção')

    def test_fora_do_horario_mostra_o_proximo_atendimento(self):
        h = self.horario(inicio=time(14, 0), fim=time(15, 0))
        self.pedido(h)
        self.entrar()
        r = self.client.get(reverse('monitor_painel'))
        self.assertEqual(r.context['resumo'].estado, 'indisponivel')
        self.assertContains(r, 'Próximo atendimento')
        self.assertContains(r, 'às 14:00, com Ana')
        self.assertContains(r, 'Confirmar remoção')    #ainda não começou: pode remover

    def test_sem_horarios_cadastrados_orienta_a_cadastrar(self):
        self.entrar()
        r = self.client.get(reverse('monitor_painel'))
        self.assertContains(r, 'ainda não cadastrou horários')
        self.assertContains(r, reverse('monitor_horarios'))

    def test_com_horarios_e_sem_pedidos_mostra_estado_vazio(self):
        self.horario(inicio=time(14, 0), fim=time(15, 0))
        self.entrar()
        self.assertContains(self.client.get(reverse('monitor_painel')), 'Nenhum aluno solicitou atendimento')

    def test_mostra_so_os_pedidos_do_proprio_monitor(self):
        self.pedido(self.horario(inicio=time(14, 0), fim=time(15, 0)), assunto='Meu assunto')
        h2 = self.horario(inicio=time(14, 0), fim=time(15, 0), monitor=self.outro)
        self.pedido(h2, assunto='Assunto da Carla')
        self.entrar()
        r = self.client.get(reverse('monitor_painel'))
        self.assertContains(r, 'Meu assunto')
        self.assertNotContains(r, 'Assunto da Carla')

    def test_pedidos_terminados_vao_para_o_historico(self):
        h = self.horario(inicio=time(8, 0), fim=time(9, 0))
        self.pedido(h, assunto='Aconteceu hoje cedo')
        self.entrar()
        r = self.client.get(reverse('monitor_painel'))
        self.assertEqual(len(r.context['anteriores']), 1)
        self.assertEqual(len(r.context['proximas']), 0)
        self.assertContains(r, 'Atendimentos anteriores')

    def test_pedidos_futuros_ficam_em_ordem_de_data_e_hora(self):
        h1 = self.horario(inicio=time(14, 0), fim=time(15, 0))
        h2 = self.horario(inicio=time(16, 0), fim=time(17, 0))
        proxima_semana = date(2026, 11, 11)
        self.pedido(h1, data=proxima_semana)
        self.pedido(h2, data=HOJE)
        self.pedido(h1, data=HOJE)
        self.entrar()
        ordem = [(s.data, s.horario.hora_inicio) for s in self.client.get(reverse('monitor_painel')).context['proximas']]
        self.assertEqual(ordem, sorted(ordem))


class RemoverAtendimentoTests(BaseTeste):
    def test_remove_e_o_horario_volta_a_ficar_livre(self):
        h = self.horario(inicio=time(14, 0), fim=time(15, 0))
        s = self.pedido(h)
        self.entrar()
        r = self.client.post(reverse('monitor_atendimento_remover', args=[s.id]), follow=True)
        self.assertFalse(Solicitacao.objects.filter(pk=s.pk).exists())
        self.assertContains(r, 'Atendimento removido')
        self.assertContains(r, 'com Ana')

    def test_nao_remove_pedido_de_outro_monitor(self):
        h = self.horario(inicio=time(14, 0), fim=time(15, 0), monitor=self.outro)
        s = self.pedido(h)
        self.entrar()
        r = self.client.post(reverse('monitor_atendimento_remover', args=[s.id]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Solicitacao.objects.filter(pk=s.pk).exists())

    def test_nao_remove_atendimento_que_ja_comecou(self):
        s = self.pedido(self.horario())  #10:00-11:00, agora são 10:30
        self.entrar()
        r = self.client.post(reverse('monitor_atendimento_remover', args=[s.id]), follow=True)
        self.assertTrue(Solicitacao.objects.filter(pk=s.pk).exists())
        self.assertContains(r, 'já começou')

    def test_sem_login_nao_remove(self):
        s = self.pedido(self.horario(inicio=time(14, 0), fim=time(15, 0)))
        r = self.client.post(reverse('monitor_atendimento_remover', args=[s.id]))
        self.assertRedirects(r, reverse('home'))
        self.assertTrue(Solicitacao.objects.filter(pk=s.pk).exists())


class HorariosTests(BaseTeste):
    def cadastrar(self, dia='2', inicio='09:00', fim='10:00', **extra):
        return self.client.post(
            reverse('monitor_horario_novo'),
            {'dia_semana': dia, 'hora_inicio': inicio, 'hora_fim': fim, **extra},
            follow=True,
        )

    def test_lista_agrupada_por_dia(self):
        self.horario(dia=0, inicio=time(9, 0), fim=time(10, 0))
        self.horario(dia=QUARTA)
        self.entrar()
        r = self.client.get(reverse('monitor_horarios'))
        self.assertEqual([rotulo for rotulo, _ in r.context['dias']], ['Segunda-feira', 'Quarta-feira'])

    def test_cadastra_horario(self):
        self.entrar()
        r = self.cadastrar()
        self.assertContains(r, 'Horário cadastrado')
        h = Horario.objects.get(monitor=self.monitor)
        self.assertEqual((h.dia_semana, h.hora_inicio, h.hora_fim), (2, time(9, 0), time(10, 0)))

    def test_recusa_fim_antes_do_inicio(self):
        self.entrar()
        r = self.cadastrar(inicio='10:00', fim='09:00')
        self.assertContains(r, 'horário final deve ser depois do inicial')
        self.assertFalse(Horario.objects.exists())

    def test_recusa_horario_sobreposto_no_mesmo_dia(self):
        self.horario(inicio=time(9, 0), fim=time(10, 0))
        self.entrar()
        for inicio, fim in [('09:30', '10:30'), ('08:00', '09:30'), ('09:15', '09:45'), ('08:00', '11:00'), ('09:00', '10:00')]:
            r = self.cadastrar(inicio=inicio, fim=fim)
            self.assertContains(r, 'se sobrepõe', msg_prefix=f'{inicio}-{fim}')
        self.assertEqual(Horario.objects.count(), 1)

    def test_aceita_horarios_colados_e_em_outro_dia(self):
        self.horario(inicio=time(9, 0), fim=time(10, 0))
        self.entrar()
        self.cadastrar(inicio='10:00', fim='11:00')   #começa quando o outro termina
        self.cadastrar(inicio='08:00', fim='09:00')   #termina quando o outro começa
        self.cadastrar(dia='3', inicio='09:00', fim='10:00')  #mesmo horário, outro dia
        self.assertEqual(Horario.objects.count(), 4)

    def test_sobreposicao_so_conta_para_o_mesmo_monitor(self):
        self.horario(inicio=time(9, 0), fim=time(10, 0), monitor=self.outro)
        self.entrar()
        self.assertContains(self.cadastrar(), 'Horário cadastrado')

    def test_dados_invalidos_nao_quebram(self):
        self.entrar()
        for dados in [dict(dia='x'), dict(dia='9'), dict(dia=''), dict(inicio=''), dict(fim='abc')]:
            r = self.cadastrar(**dados)
            self.assertEqual(r.status_code, 200)
        self.assertFalse(Horario.objects.exists())

    def test_remove_horario_sem_atendimentos(self):
        h = self.horario()
        self.entrar()
        r = self.client.post(reverse('monitor_horario_remover', args=[h.id]), follow=True)
        self.assertContains(r, 'Horário removido')
        self.assertFalse(Horario.objects.exists())

    def test_nao_remove_horario_com_atendimento_marcado(self):
        h = self.horario(inicio=time(14, 0), fim=time(15, 0))
        s = self.pedido(h)
        self.entrar()
        r = self.client.post(reverse('monitor_horario_remover', args=[h.id]), follow=True)
        self.assertContains(r, '1 atendimento marcado')
        self.assertTrue(Horario.objects.filter(pk=h.pk).exists())
        self.assertTrue(Solicitacao.objects.filter(pk=s.pk).exists())  #o pedido do aluno não some

    def test_atendimento_ja_terminado_nao_impede_remover_o_horario(self):
        h = self.horario(inicio=time(8, 0), fim=time(9, 0))
        self.pedido(h)
        self.entrar()
        self.client.post(reverse('monitor_horario_remover', args=[h.id]))
        self.assertFalse(Horario.objects.filter(pk=h.pk).exists())

    def test_nao_remove_horario_de_outro_monitor(self):
        h = self.horario(monitor=self.outro)
        self.entrar()
        self.assertEqual(self.client.post(reverse('monitor_horario_remover', args=[h.id])).status_code, 404)
        self.assertTrue(Horario.objects.filter(pk=h.pk).exists())

    def test_o_aluno_enxerga_o_horario_recem_cadastrado(self):
        self.entrar()
        self.cadastrar(dia=str(HOJE.weekday()), inicio='14:00', fim='15:00')
        cliente_do_aluno = Client()
        sessao = cliente_do_aluno.session
        sessao['aluno_id'] = self.aluno.id
        sessao.save()
        with patch('interface_aluno.views.agora_local', return_value=AGORA):
            r = cliente_do_aluno.get(reverse('monitor_detalhe', args=[self.monitor.id]))
        self.assertContains(r, '14:00 às 15:00')


class RegrasDoModelTests(BaseTeste):
    def test_horario_nao_conflita_consigo_mesmo_ao_ser_editado(self):
        h = self.horario()
        h.hora_fim = time(11, 30)
        h.full_clean()  #não deve levantar erro

    def test_editar_para_cima_de_outro_horario_e_recusado(self):
        self.horario(inicio=time(11, 0), fim=time(12, 0))
        h = self.horario(inicio=time(9, 0), fim=time(10, 0))
        h.hora_fim = time(11, 30)
        with self.assertRaises(ValidationError):
            h.full_clean()

    def test_clean_sem_monitor_ainda_nao_quebra(self):
        #é o caso do admin ao criar um monitor novo com horários na mesma tela
        Horario(dia_semana=2, hora_inicio=time(9, 0), hora_fim=time(10, 0)).clean()


class AdminTests(BaseTeste):
    def test_senha_digitada_no_admin_e_guardada_com_hash(self):
        class FormFalso:
            changed_data = ['senha']

        monitor = Monitor(matricula='m7', nome='Pelo admin', senha='texto-puro')
        MonitorAdmin(Monitor, admin.site).save_model(RequestFactory().post('/'), monitor, FormFalso(), False)
        monitor.refresh_from_db()
        self.assertNotEqual(monitor.senha, 'texto-puro')
        self.assertTrue(check_password('texto-puro', monitor.senha))

    def test_salvar_sem_mexer_na_senha_nao_faz_hash_do_hash(self):
        class FormFalso:
            changed_data = ['nome']

        antes = self.monitor.senha
        self.monitor.nome = 'Outro nome'
        MonitorAdmin(Monitor, admin.site).save_model(RequestFactory().post('/'), self.monitor, FormFalso(), True)
        self.monitor.refresh_from_db()
        self.assertEqual(self.monitor.senha, antes)


class StatusManualTests(BaseTeste):
    """O monitor sobrepõe, por tempo limitado, o estado calculado pelos horários."""

    def definir(self, status, minutos, monitor=None):
        m = monitor or self.monitor
        Monitor.objects.filter(pk=m.pk).update(
            status_manual=status, status_manual_ate=AGORA + timedelta(minutes=minutos))

    def estado_no_painel(self):
        self.entrar()
        return self.client.get(reverse('monitor_painel')).context['resumo']

    def aluno_ve(self, url_name, *args, **params):
        cliente = Client()
        sessao = cliente.session
        sessao['aluno_id'] = self.aluno.id
        sessao.save()
        with patch('interface_aluno.views.agora_local', return_value=AGORA):
            return cliente.get(reverse(url_name, args=args), params)

    # ---------- como o estado é calculado ----------

    def test_sem_status_manual_nada_muda(self):
        self.horario()
        r = self.estado_no_painel()
        self.assertEqual((r.estado, r.manual), ('disponivel', False))

    def test_indisponivel_manual_vence_o_horario_livre(self):
        self.horario()  #10:00-11:00, agora são 10:30
        self.definir('indisponivel', 30)
        r = self.estado_no_painel()
        self.assertEqual((r.estado, r.estado_automatico, r.manual), ('indisponivel', 'disponivel', True))

    def test_indisponivel_manual_vence_ate_o_atendimento_solicitado(self):
        self.pedido(self.horario())
        self.definir('indisponivel', 30)
        r = self.estado_no_painel()
        self.assertEqual((r.estado, r.estado_automatico), ('indisponivel', 'em_atendimento'))

    def test_disponivel_manual_vale_fora_do_horario(self):
        self.horario(inicio=time(14, 0), fim=time(15, 0))
        self.definir('disponivel', 60)
        r = self.estado_no_painel()
        self.assertEqual((r.estado, r.estado_automatico, r.manual), ('disponivel', 'indisponivel', True))
        self.assertEqual(r.disponivel_ate, time(11, 30))

    def test_disponivel_manual_nao_passa_por_cima_de_atendimento_solicitado(self):
        self.pedido(self.horario())
        self.definir('disponivel', 60)
        r = self.estado_no_painel()
        self.assertEqual((r.estado, r.manual), ('em_atendimento', False))

    def test_status_manual_vencido_e_ignorado(self):
        self.horario()
        self.definir('indisponivel', -1)  #venceu há um minuto
        r = self.estado_no_painel()
        self.assertEqual((r.estado, r.manual), ('disponivel', False))

    def test_status_manual_e_so_do_monitor_que_o_definiu(self):
        self.horario(monitor=self.outro)
        self.definir('indisponivel', 30)  #do monitor, não da Carla
        self.entrar(self.outro)
        self.assertEqual(self.client.get(reverse('monitor_painel')).context['resumo'].estado, 'disponivel')

    # ---------- a view que altera o status ----------

    def post(self, **dados):
        return self.client.post(reverse('monitor_status'), dados, follow=True)

    def test_fica_indisponivel_por_o_tempo_escolhido(self):
        self.horario()
        self.entrar()
        r = self.post(status='indisponivel', duracao='30')
        self.monitor.refresh_from_db()
        self.assertEqual(self.monitor.status_manual, 'indisponivel')
        self.assertEqual(self.monitor.status_manual_ate, AGORA + timedelta(minutes=30))
        self.assertContains(r, 'indisponível até 11:00')

    def test_fica_disponivel_fora_do_horario(self):
        self.horario(inicio=time(14, 0), fim=time(15, 0))
        self.entrar()
        r = self.post(status='disponivel', duracao='120')
        self.monitor.refresh_from_db()
        self.assertEqual(self.monitor.status_manual, 'disponivel')
        self.assertContains(r, 'disponível até 12:30')

    def test_disponivel_e_recusado_dentro_do_horario(self):
        self.horario()
        self.entrar()
        r = self.post(status='disponivel', duracao='60')
        self.monitor.refresh_from_db()
        self.assertEqual(self.monitor.status_manual, '')
        self.assertContains(r, 'dentro de um horário de atendimento')

    def test_voltar_ao_automatico_limpa(self):
        self.horario()
        self.definir('indisponivel', 60)
        self.entrar()
        self.post(status='automatico')
        self.monitor.refresh_from_db()
        self.assertEqual((self.monitor.status_manual, self.monitor.status_manual_ate), ('', None))

    def test_dados_invalidos_nao_alteram_nada(self):
        self.entrar()
        for dados in [dict(status='x', duracao='30'), dict(status='indisponivel', duracao='5'),
                      dict(status='indisponivel', duracao='abc'), dict(status='indisponivel'), dict()]:
            r = self.post(**dados)
            self.assertEqual(r.status_code, 200)
        self.monitor.refresh_from_db()
        self.assertEqual(self.monitor.status_manual, '')

    def test_exige_login_e_post(self):
        r = self.client.post(reverse('monitor_status'), dict(status='indisponivel', duracao='30'))
        self.assertRedirects(r, reverse('home'))
        self.entrar()
        self.assertEqual(self.client.get(reverse('monitor_status')).status_code, 405)

    # ---------- o que o monitor vê no painel ----------

    def test_painel_oferece_o_botao_certo_para_cada_situacao(self):
        self.horario(inicio=time(14, 0), fim=time(15, 0))
        self.entrar()
        self.assertContains(self.client.get(reverse('monitor_painel')), 'Ficar disponível agora')
        Horario.objects.all().delete()
        self.horario()
        self.assertContains(self.client.get(reverse('monitor_painel')), 'Ficar indisponível agora')

    def test_painel_com_status_manual_mostra_ate_quando_e_como_voltar(self):
        self.horario()
        self.definir('indisponivel', 30)
        self.entrar()
        r = self.client.get(reverse('monitor_painel'))
        self.assertContains(r, 'Você marcou que está indisponível até 11:00')
        self.assertContains(r, 'Voltar ao automático')
        self.assertNotContains(r, 'Ficar indisponível agora')

    # ---------- o que o ALUNO vê ----------

    def test_aluno_ve_o_monitor_indisponivel_na_lista_e_no_detalhe(self):
        self.horario()
        self.definir('indisponivel', 30)
        lista = self.aluno_ve('painel')
        self.assertContains(lista, 'Indisponível agora')
        self.assertContains(lista, 'Indisponível até 11:00')
        detalhe = self.aluno_ve('monitor_detalhe', self.monitor.id)
        self.assertContains(detalhe, 'marcou que está indisponível até 11:00')
        self.assertNotContains(detalhe, 'Atende até')

    def test_aluno_ve_disponivel_manual_com_a_hora_certa_e_no_filtro_agora(self):
        self.horario(inicio=time(14, 0), fim=time(15, 0))
        self.definir('disponivel', 60)
        lista = self.aluno_ve('painel', disponibilidade='agora')
        self.assertContains(lista, 'Atende até 11:30')  #nunca "Atende até " em branco
        self.assertContains(lista, 'Breno')
        detalhe = self.aluno_ve('monitor_detalhe', self.monitor.id)
        self.assertContains(detalhe, 'marcou que está disponível até 11:30')

    def test_status_manual_nao_impede_o_aluno_de_solicitar_horarios_livres(self):
        h = self.horario(inicio=time(14, 0), fim=time(15, 0))
        self.definir('indisponivel', 120)
        cliente = Client()
        sessao = cliente.session
        sessao['aluno_id'] = self.aluno.id
        sessao.save()
        with patch('interface_aluno.views.agora_local', return_value=AGORA):
            cliente.post(reverse('solicitar_horario', args=[h.id]), {
                'data': HOJE.isoformat(), 'assunto': 'Teste', 'formato': 'online', 'participantes': 'individual'})
        self.assertTrue(Solicitacao.objects.filter(horario=h, data=HOJE).exists())


class DisciplinasTests(BaseTeste):
    def setUp(self):
        super().setUp()
        self.calc = Disciplina.objects.create(codigo='MAT01', nome='Cálculo I')
        self.alg = Disciplina.objects.create(codigo='MAT02', nome='Álgebra Linear')
        self.entrar()

    def salvar(self, *ids):
        return self.client.post(reverse('monitor_disciplinas_salvar'), {'disciplinas': [str(i) for i in ids]}, follow=True)

    def nova(self, codigo='FIS01', nome='Física I'):
        return self.client.post(reverse('monitor_disciplina_nova'), {'codigo': codigo, 'nome': nome}, follow=True)

    def minhas(self, monitor=None):
        return set((monitor or self.monitor).disciplinas.values_list('codigo', flat=True))

    # ---------- escolher entre as existentes ----------

    def test_tela_lista_todas_e_marca_as_do_monitor(self):
        self.monitor.disciplinas.add(self.calc)
        r = self.client.get(reverse('monitor_disciplinas'))
        self.assertEqual(r.context['marcadas'], {self.calc.id})
        self.assertContains(r, 'Álgebra Linear')
        self.assertContains(r, 'Cálculo I')

    def test_tela_lista_as_disciplinas_em_ordem_de_nome(self):
        Disciplina.objects.all().delete()
        Disciplina.objects.create(codigo='Z1', nome='Zoologia')   #sem acento: a ordem de letras acentuadas
        Disciplina.objects.create(codigo='A1', nome='Algoritmos') #varia conforme o banco
        r = self.client.get(reverse('monitor_disciplinas'))
        self.assertEqual([d.codigo for d in r.context['todas']], ['A1', 'Z1'])

    def test_salva_marcando_e_desmarcando(self):
        self.salvar(self.calc.id, self.alg.id)
        self.assertEqual(self.minhas(), {'MAT01', 'MAT02'})
        r = self.salvar(self.alg.id)  #tirou Cálculo
        self.assertEqual(self.minhas(), {'MAT02'})
        self.assertContains(r, 'você atende em 1')
        self.assertTrue(Disciplina.objects.filter(pk=self.calc.pk).exists())  #a disciplina continua existindo

    def test_pode_ficar_sem_nenhuma(self):
        self.monitor.disciplinas.add(self.calc)
        r = self.salvar()
        self.assertEqual(self.minhas(), set())
        self.assertContains(r, 'não está associado a nenhuma')

    def test_ids_invalidos_sao_ignorados(self):
        self.client.post(reverse('monitor_disciplinas_salvar'), {'disciplinas': ['999999', 'abc', str(self.calc.id)]})
        self.assertEqual(self.minhas(), {'MAT01'})

    def test_salvar_nao_mexe_nas_disciplinas_de_outro_monitor(self):
        self.outro.disciplinas.add(self.alg)
        self.salvar(self.calc.id)
        self.assertEqual(self.minhas(self.outro), {'MAT02'})

    # ---------- cadastrar uma que não existe ----------

    def test_cadastra_disciplina_nova_e_associa_ao_monitor(self):
        r = self.nova('fis01', '  Física   I ')
        d = Disciplina.objects.get(codigo='FIS01')           #código em maiúsculas
        self.assertEqual(d.nome, 'Física I')                 #espaços sobrando removidos
        self.assertEqual(self.minhas(), {'FIS01'})
        self.assertContains(r, 'Disciplina cadastrada')

    def test_codigo_ja_existente_reaproveita_sem_trocar_o_nome(self):
        r = self.nova('mat01', 'Outro nome qualquer')         #mesmo código, outras maiúsculas
        self.assertEqual(Disciplina.objects.filter(codigo__iexact='MAT01').count(), 1)
        self.calc.refresh_from_db()
        self.assertEqual(self.calc.nome, 'Cálculo I')
        self.assertEqual(self.minhas(), {'MAT01'})
        self.assertContains(r, 'Já existia uma disciplina com o código MAT01')

    def test_validacoes_do_cadastro(self):
        for codigo, nome, trecho in [('', 'Física I', 'Informe o código e o nome'),
                                     ('FIS01', '   ', 'Informe o código e o nome'),
                                     ('X' * 21, 'Física I', 'no máximo 20'),
                                     ('FIS01', 'N' * 101, 'no máximo 100')]:
            self.assertContains(self.nova(codigo, nome), trecho)
        self.assertFalse(Disciplina.objects.filter(codigo__startswith='FIS').exists())
        self.assertEqual(self.minhas(), set())

    def test_sem_nenhuma_disciplina_no_sistema_oferece_o_cadastro(self):
        Disciplina.objects.all().delete()
        r = self.client.get(reverse('monitor_disciplinas'))
        self.assertContains(r, 'Ainda não há nenhuma disciplina cadastrada')
        self.assertContains(r, 'Cadastrar e usar')

    # ---------- acesso e integração ----------

    def test_exige_login_e_post(self):
        sem_login = Client()  #o self.client já está logado (setUp)
        self.assertRedirects(sem_login.get(reverse('monitor_disciplinas')), reverse('home'))
        for nome in ['monitor_disciplinas_salvar', 'monitor_disciplina_nova']:
            self.assertRedirects(sem_login.post(reverse(nome), {}), reverse('home'))
            self.assertEqual(self.client.get(reverse(nome)).status_code, 405)

    def test_painel_sem_disciplinas_mostra_atalho_para_adicionar(self):
        r = self.client.get(reverse('monitor_painel'))
        self.assertContains(r, 'Nenhuma disciplina cadastrada')
        self.assertContains(r, reverse('monitor_disciplinas'))
        self.monitor.disciplinas.add(self.calc)
        r = self.client.get(reverse('monitor_painel'))
        self.assertNotContains(r, 'Nenhuma disciplina cadastrada')
        self.assertContains(r, 'Cálculo I')

    def test_aluno_passa_a_encontrar_o_monitor_pela_disciplina_nova(self):
        self.nova('FIS01', 'Física I')
        d = Disciplina.objects.get(codigo='FIS01')
        cliente = Client()
        sessao = cliente.session
        sessao['aluno_id'] = self.aluno.id
        sessao.save()
        with patch('interface_aluno.views.agora_local', return_value=AGORA):
            lista = cliente.get(reverse('painel'), {'disciplina': d.id})
        self.assertContains(lista, 'Física I')       #aparece no filtro
        self.assertContains(lista, 'Breno')          #e o monitor aparece filtrado por ela
