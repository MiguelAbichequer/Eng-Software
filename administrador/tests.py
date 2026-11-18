"""
Testes da área do administrador: consultar e expulsar usuários.

O "agora" é fixado (quarta-feira, 04/11/2026, 10:30) para o resultado não depender do relógio.
Para rodar:  python manage.py test administrador
"""

import os
import shutil
import tempfile
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno
from monitor.models import Disciplina, DiasSemana, Horario, Monitor, Solicitacao

from .models import Denuncia

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


class AprovacaoDeMonitorTests(BaseTeste):
    """Monitor que se cadastra pela página inicial só vale depois da aprovação do administrador."""

    def setUp(self):
        super().setUp()
        #os documentos enviados no cadastro vão para uma pasta temporária
        pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, pasta, True)
        override = override_settings(MEDIA_ROOT=pasta)
        override.enable()
        self.addCleanup(override.disable)

    def cadastrar_monitor(self, matricula='m9', nome='Diego Novo'):
        documento = SimpleUploadedFile('diploma.pdf', b'%PDF-1.4 teste', content_type='application/pdf')
        self.client.post(reverse('cadastro_monitor'), {
            'matricula': matricula, 'nome': nome, 'senha': 'segredo', 'documento': documento,
        })
        return Monitor.objects.get(matricula=matricula)

    def entrar_como_monitor(self, matricula='m9'):
        return self.client.post('/', {'tipo': 'monitor', 'username': matricula, 'password': 'segredo'})

    def test_cadastro_pela_pagina_inicial_fica_aguardando(self):
        novo = self.cadastrar_monitor()
        self.assertFalse(novo.aprovado)
        self.assertIsNotNone(novo.cadastrado_em)

    def test_monitor_criado_pelo_codigo_ou_admin_ja_e_aprovado(self):
        self.assertTrue(self.monitor.aprovado)

    def test_aguardando_nao_consegue_entrar(self):
        self.cadastrar_monitor()
        r = self.entrar_como_monitor()
        self.assertContains(r, 'aguardando a aprovação')
        self.assertNotIn('monitor_id', self.client.session)

    def test_senha_errada_nao_revela_que_esta_aguardando(self):
        self.cadastrar_monitor()
        r = self.client.post('/', {'tipo': 'monitor', 'username': 'm9', 'password': 'errada'})
        self.assertContains(r, 'Senha incorreta')
        self.assertNotContains(r, 'aguardando')

    def test_aguardando_nao_aparece_para_os_alunos(self):
        novo = self.cadastrar_monitor()
        Horario.objects.create(monitor=novo, dia_semana=QUARTA, hora_inicio=time(16), hora_fim=time(17))
        sessao = self.client.session
        sessao['aluno_id'] = self.aluno.id
        sessao.save()
        painel = self.client.get(reverse('painel'))
        self.assertNotIn(novo, [r.monitor for r in painel.context['resumos']])
        self.assertEqual(self.client.get(reverse('monitor_detalhe', args=[novo.id])).status_code, 404)

    def test_fila_lista_os_pendentes_e_o_menu_mostra_o_numero(self):
        self.cadastrar_monitor()
        self.entrar_admin()
        r = self.client.get(reverse('monitores_pendentes'))
        self.assertEqual([m.nome for m in r.context['pendentes']], ['Diego Novo'])
        self.assertContains(r, 'class="contador"')
        self.assertNotContains(r, 'Carla')  #já aprovado: não aparece na fila

    def test_aprovar_libera_o_login(self):
        novo = self.cadastrar_monitor()
        self.entrar_admin()
        r = self.client.post(reverse('monitor_aprovar', args=[novo.id]), follow=True)
        self.assertContains(r, 'foi aprovado como monitor')
        novo.refresh_from_db()
        self.assertTrue(novo.aprovado)

        self.client.logout()
        self.assertRedirects(self.entrar_como_monitor(), reverse('monitor_painel'), fetch_redirect_response=False)

    def test_recusar_apaga_o_cadastro_e_libera_a_matricula(self):
        novo = self.cadastrar_monitor()
        self.entrar_admin()
        r = self.client.post(reverse('monitor_recusar', args=[novo.id]), follow=True)
        self.assertContains(r, 'foi recusado e apagado')
        self.assertFalse(Monitor.objects.filter(matricula='m9').exists())

        self.client.logout()
        self.assertFalse(self.cadastrar_monitor().aprovado)  #pode se cadastrar de novo

    def test_so_vale_para_pendentes(self):
        self.entrar_admin()
        #monitor já aprovado não pode ser "recusado" (apagado) por esta tela
        self.assertEqual(self.client.post(reverse('monitor_recusar', args=[self.monitor.id])).status_code, 404)
        self.assertTrue(Monitor.objects.filter(pk=self.monitor.pk).exists())

    def test_exige_administrador_e_post(self):
        novo = self.cadastrar_monitor()
        r = self.client.post(reverse('monitor_aprovar', args=[novo.id]))
        self.assertIn(reverse('admin:login'), r['Location'])
        novo.refresh_from_db()
        self.assertFalse(novo.aprovado)

        self.entrar_admin()
        self.assertEqual(self.client.get(reverse('monitor_aprovar', args=[novo.id])).status_code, 405)

    def test_lista_e_ficha_de_usuarios_mostram_aguardando(self):
        novo = self.cadastrar_monitor()
        self.entrar_admin()
        self.assertContains(self.client.get(reverse('usuarios')), 'Aguardando aprovação')
        ficha = self.client.get(reverse('usuario', args=['monitor', novo.id]))
        self.assertContains(ficha, 'Cadastro aguardando aprovação')
        self.assertContains(ficha, reverse('monitor_aprovar', args=[novo.id]))


@patch('interface_monitor.views.agora_local', return_value=AGORA)
class DenunciaTests(BaseTeste):
    """O monitor denuncia um aluno; o administrador expulsa ou arquiva."""

    def setUp(self):
        super().setUp()
        self.pedido(self.tarde_h)  #Ana tem um atendimento com Carla

    def entrar_monitor(self, monitor=None):
        sessao = self.client.session
        sessao['monitor_id'] = (monitor or self.monitor).id
        sessao.save()

    def denunciar(self, aluno=None, motivo='Faltou sem avisar três vezes'):
        return self.client.post(reverse('monitor_denunciar', args=[(aluno or self.aluno).id]), {'motivo': motivo}, follow=True)

    # --- o monitor denuncia ---

    def test_monitor_denuncia_um_aluno_que_ele_atendeu(self, _):
        self.entrar_monitor()
        r = self.denunciar(motivo='  Faltou   sem avisar ')
        self.assertContains(r, 'Denúncia sobre Ana enviada ao administrador')
        d = Denuncia.objects.get()
        self.assertEqual((d.aluno, d.monitor, d.motivo, d.situacao), (self.aluno, self.monitor, 'Faltou sem avisar', 'pendente'))

    def test_painel_do_monitor_oferece_denunciar(self, _):
        self.entrar_monitor()
        r = self.client.get(reverse('monitor_painel'))
        self.assertContains(r, 'Denunciar aluno')
        self.assertContains(r, reverse('monitor_denunciar', args=[self.aluno.id]))

    def test_nao_denuncia_aluno_que_nunca_atendeu(self, _):
        self.entrar_monitor()
        r = self.client.post(reverse('monitor_denunciar', args=[self.outro_aluno.id]), {'motivo': 'x'})
        self.assertEqual(r.status_code, 404)
        self.assertFalse(Denuncia.objects.exists())

    def test_motivo_vazio_ou_longo_e_recusado(self, _):
        self.entrar_monitor()
        self.assertContains(self.denunciar(motivo='   '), 'Explique o motivo')
        self.assertContains(self.denunciar(motivo='x' * 501), 'no máximo 500')
        self.assertFalse(Denuncia.objects.exists())

    def test_denunciar_exige_monitor_logado_e_post(self, _):
        r = self.client.post(reverse('monitor_denunciar', args=[self.aluno.id]), {'motivo': 'x'})
        self.assertRedirects(r, reverse('home'), fetch_redirect_response=False)
        self.entrar_monitor()
        self.assertEqual(self.client.get(reverse('monitor_denunciar', args=[self.aluno.id])).status_code, 405)
        self.assertFalse(Denuncia.objects.exists())

    # --- o administrador decide ---

    def criar(self, motivo='Desrespeitou o monitor'):
        return Denuncia.objects.create(aluno=self.aluno, monitor=self.monitor, motivo=motivo)

    def test_tela_lista_pendentes_e_o_menu_mostra_o_numero(self, _):
        self.criar()
        self.entrar_admin()
        r = self.client.get(reverse('denuncias'))
        self.assertEqual(len(r.context['pendentes']), 1)
        self.assertContains(r, 'Desrespeitou o monitor')
        self.assertContains(r, 'Denúncias <span class="contador"')

    def test_expulsar_usa_a_expulsao_normal_e_resolve_as_pendentes_do_aluno(self, _):
        d1, d2 = self.criar('Primeira'), self.criar('Segunda')
        self.entrar_admin()
        r = self.client.post(reverse('denuncia_expulsar', args=[d1.id]), follow=True)
        self.assertContains(r, 'Ana foi expulso')
        self.aluno.refresh_from_db()
        self.assertTrue(self.aluno.expulso)
        self.assertEqual(self.aluno.motivo_expulsao, 'Denúncia de Carla: Primeira')
        self.assertEqual(set(Denuncia.objects.values_list('situacao', flat=True)), {'expulso'})
        self.assertFalse(Solicitacao.objects.exists())  #o atendimento futuro dela foi cancelado

    def test_motivo_longo_e_cortado_na_expulsao(self, _):
        d = self.criar('x' * 400)
        self.entrar_admin()
        self.client.post(reverse('denuncia_expulsar', args=[d.id]))
        self.aluno.refresh_from_db()
        self.assertEqual(len(self.aluno.motivo_expulsao), 200)
        self.assertTrue(self.aluno.motivo_expulsao.endswith('...'))

    def test_arquivar_nao_pune(self, _):
        d = self.criar()
        self.entrar_admin()
        r = self.client.post(reverse('denuncia_arquivar', args=[d.id]), follow=True)
        self.assertContains(r, 'arquivada, sem punição')
        self.aluno.refresh_from_db()
        self.assertFalse(self.aluno.expulso)
        d.refresh_from_db()
        self.assertEqual(d.situacao, 'arquivada')
        self.assertIsNotNone(d.resolvida_em)

    def test_denuncia_resolvida_nao_pode_ser_decidida_de_novo(self, _):
        d = self.criar()
        self.entrar_admin()
        self.client.post(reverse('denuncia_arquivar', args=[d.id]))
        self.assertEqual(self.client.post(reverse('denuncia_expulsar', args=[d.id])).status_code, 404)

    def test_ficha_do_aluno_mostra_as_denuncias(self, _):
        self.criar()
        self.entrar_admin()
        r = self.client.get(self.url('usuario', 'aluno', self.aluno))
        self.assertContains(r, 'Denúncias recebidas')
        self.assertContains(r, 'Desrespeitou o monitor')

    def test_decidir_exige_administrador(self, _):
        d = self.criar()
        r = self.client.post(reverse('denuncia_expulsar', args=[d.id]))
        self.assertIn(reverse('admin:login'), r['Location'])
        self.aluno.refresh_from_db()
        self.assertFalse(self.aluno.expulso)


class AprovacaoAlunoTests(TestCase):
    """Fila de cadastros de aluno: o administrador confere o documento e aprova ou recusa."""

    def setUp(self):
        #os documentos vão para uma pasta temporária, não para o projeto
        pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, pasta, True)
        override = override_settings(MEDIA_ROOT=pasta)
        override.enable()
        self.addCleanup(override.disable)

        self.admin = User.objects.create_user('admin', password='x', is_staff=True)
        self.comprovante = SimpleUploadedFile('comprovante.pdf', b'%PDF-1.4 conteudo', content_type='application/pdf')
        self.pendente = Aluno.objects.create(
            matricula='p1', nome='Paula', senha=HASH, aprovado=False,
            documento_confirmacao=self.comprovante,
        )

    def test_fila_mostra_o_pendente_e_o_link_do_documento(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('alunos_pendentes'))
        self.assertContains(r, 'Paula')
        self.assertContains(r, reverse('aluno_documento', args=[self.pendente.id]))

    def test_documento_so_abre_para_o_administrador(self):
        url = reverse('aluno_documento', args=[self.pendente.id])
        r = self.client.get(url)
        self.assertNotEqual(r.status_code, 200)  #visitante não vê o documento

        self.client.force_login(self.admin)
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b''.join(r.streaming_content), b'%PDF-1.4 conteudo')
        self.assertIn('inline', r['Content-Disposition'])

    def test_aprovar_libera_o_aluno(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse('aluno_aprovar', args=[self.pendente.id]))
        self.assertRedirects(r, reverse('alunos_pendentes'), fetch_redirect_response=False)
        self.pendente.refresh_from_db()
        self.assertTrue(self.pendente.aprovado)
        #o documento fica guardado para conferência posterior
        self.assertTrue(self.pendente.documento_confirmacao)

    def test_recusar_apaga_a_conta_e_o_documento(self):
        caminho = self.pendente.documento_confirmacao.path
        self.client.force_login(self.admin)
        self.client.post(reverse('aluno_recusar', args=[self.pendente.id]))
        self.assertFalse(Aluno.objects.filter(pk=self.pendente.pk).exists())
        self.assertFalse(os.path.exists(caminho))

    def test_aprovar_ou_recusar_so_vale_para_pendentes_e_por_post(self):
        aprovado = Aluno.objects.create(matricula='ok', nome='Ok', senha=HASH)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('aluno_aprovar', args=[aprovado.id])).status_code, 404)
        self.assertEqual(self.client.post(reverse('aluno_recusar', args=[aprovado.id])).status_code, 404)
        self.assertTrue(Aluno.objects.filter(pk=aprovado.pk).exists())

        self.assertEqual(self.client.get(reverse('aluno_aprovar', args=[self.pendente.id])).status_code, 405)
        self.pendente.refresh_from_db()
        self.assertFalse(self.pendente.aprovado)

    def test_contador_do_menu_conta_os_pendentes(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('alunos_pendentes'))
        self.assertEqual(r.context['alunos_pendentes_total'], 1)


class AprovacaoMonitorDocumentoTests(TestCase):
    """O monitor também envia documento de confirmação, conferido pelo administrador."""

    def setUp(self):
        pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, pasta, True)
        override = override_settings(MEDIA_ROOT=pasta)
        override.enable()
        self.addCleanup(override.disable)

        self.admin = User.objects.create_user('admin', password='x', is_staff=True)
        self.pendente = Monitor.objects.create(
            matricula='mp1', nome='Marcos', senha=HASH, aprovado=False,
            documento_confirmacao=SimpleUploadedFile('diploma.pdf', b'%PDF-1.4 monitor', content_type='application/pdf'),
        )

    def test_documento_do_monitor_so_abre_para_o_administrador(self):
        url = reverse('monitor_documento', args=[self.pendente.id])
        self.assertNotEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.admin)
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b''.join(r.streaming_content), b'%PDF-1.4 monitor')

    def test_fila_de_monitor_mostra_o_link_do_documento(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('monitores_pendentes'))
        self.assertContains(r, reverse('monitor_documento', args=[self.pendente.id]))

    def test_recusar_monitor_apaga_o_documento(self):
        caminho = self.pendente.documento_confirmacao.path
        self.client.force_login(self.admin)
        self.client.post(reverse('monitor_recusar', args=[self.pendente.id]))
        self.assertFalse(Monitor.objects.filter(pk=self.pendente.pk).exists())
        self.assertFalse(os.path.exists(caminho))
