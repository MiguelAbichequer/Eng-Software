"""
Testes da página inicial (login) e dos cadastros de aluno e monitor.

Para rodar:  python manage.py test inicio
"""

import shutil
import tempfile

from django.contrib.auth.hashers import check_password, make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from alunos.models import Aluno
from monitor.models import Monitor


class CadastroTests(TestCase):
    #os dois cadastros usam a mesma regra (inicio/cadastro.py): cada teste roda para os dois
    CASOS = [('cadastro_aluno', Aluno, 'aluno'), ('cadastro_monitor', Monitor, 'monitor')]

    def setUp(self):
        #os documentos de confirmação vão para uma pasta temporária, não para o projeto
        pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, pasta, True)
        override = override_settings(MEDIA_ROOT=pasta)
        override.enable()
        self.addCleanup(override.disable)

    def documento_valido(self, nome='comprovante.pdf', conteudo=b'%PDF-1.4 teste'):
        return SimpleUploadedFile(nome, conteudo, content_type='application/pdf')

    def enviar(self, rota, **dados):
        campos = {'matricula': '2024001', 'nome': 'Ana Ribeiro', 'senha': 'abc123'}
        #aluno e monitor enviam um documento de confirmação
        if rota in ('cadastro_aluno', 'cadastro_monitor'):
            campos['documento'] = self.documento_valido()
        campos.update(dados)
        return self.client.post(reverse(rota), campos)

    def test_pagina_abre(self):
        for rota, _, papel in self.CASOS:
            with self.subTest(papel):
                r = self.client.get(reverse(rota))
                self.assertContains(r, f'Cadastro de {papel}')

    def test_cadastra_confirma_e_volta_para_o_login_com_o_papel_marcado(self):
        for rota, modelo, papel in self.CASOS:
            with self.subTest(papel):
                r = self.enviar(rota)
                #fetch_redirect_response=False: senão o teste abre a página antes e "gasta" a mensagem
                self.assertRedirects(r, reverse('home') + f'?tipo={papel}', fetch_redirect_response=False)

                novo = modelo.objects.get(matricula='2024001')
                self.assertEqual(novo.nome, 'Ana Ribeiro')
                self.assertTrue(check_password('abc123', novo.senha))
                self.assertNotEqual(novo.senha, 'abc123')
                #aluno e monitor só entram depois da aprovação do administrador
                self.assertFalse(novo.aprovado)

                pagina = self.client.get(r['Location'])
                self.assertContains(pagina, 'Cadastro enviado, Ana!')
                self.assertContains(pagina, f'value="{papel}" checked')

    def test_matricula_repetida_mostra_erro_em_vez_de_quebrar(self):
        for rota, modelo, papel in self.CASOS:
            with self.subTest(papel):
                modelo.objects.create(matricula='2024001', nome='Já existe')
                r = self.enviar(rota)
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, 'Já existe um cadastro com essa matrícula')
                self.assertEqual(modelo.objects.filter(matricula='2024001').count(), 1)

    def test_aluno_e_monitor_podem_ter_a_mesma_matricula(self):
        #são cadastros separados: o monitor costuma ser aluno também
        self.enviar('cadastro_aluno')
        self.enviar('cadastro_monitor')
        self.assertTrue(Aluno.objects.filter(matricula='2024001').exists())
        self.assertTrue(Monitor.objects.filter(matricula='2024001').exists())

    def test_campos_vazios_ou_longos_sao_recusados_e_voltam_preenchidos(self):
        casos = {
            'sem nome': {'nome': '   '},
            'sem senha': {'senha': ''},
            'matrícula longa': {'matricula': '1' * 21},
            'nome longo': {'nome': 'a' * 101},
        }
        for nome_caso, dados in casos.items():
            with self.subTest(nome_caso):
                r = self.enviar('cadastro_aluno', **dados)
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, 'aviso-error')
        self.assertFalse(Aluno.objects.exists())

        r = self.enviar('cadastro_aluno', senha='')
        self.assertContains(r, 'value="2024001"')
        self.assertContains(r, 'value="Ana Ribeiro"')

    def test_campo_faltando_no_envio_nao_da_erro_500(self):
        r = self.client.post(reverse('cadastro_aluno'), {'matricula': '1'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Aluno.objects.exists())

    def test_espacos_sobrando_sao_limpos(self):
        self.enviar('cadastro_aluno', matricula=' 2024001 ', nome='  Ana   Ribeiro ')
        aluno = Aluno.objects.get()
        self.assertEqual((aluno.matricula, aluno.nome), ('2024001', 'Ana Ribeiro'))

    def test_aluno_sem_documento_e_recusado(self):
        r = self.client.post(reverse('cadastro_aluno'), {'matricula': '2024001', 'nome': 'Ana', 'senha': 'abc123'})
        self.assertContains(r, 'Envie o documento de confirmação')
        self.assertFalse(Aluno.objects.exists())

    def test_documento_com_formato_ou_conteudo_errado_e_recusado(self):
        casos = {
            'extensão não aceita': self.documento_valido('lista.docx', b'PK\x03\x04'),
            'nome .pdf com conteúdo de texto': self.documento_valido('foto.pdf', b'isto nao e um pdf'),
            'arquivo grande': self.documento_valido('grande.pdf', b'%PDF' + b'0' * (5 * 1024 * 1024)),
        }
        for nome_caso, arquivo in casos.items():
            with self.subTest(nome_caso):
                r = self.client.post(reverse('cadastro_aluno'), {
                    'matricula': '2024001', 'nome': 'Ana', 'senha': 'abc123', 'documento': arquivo,
                })
                self.assertContains(r, 'aviso-error')
                self.assertFalse(Aluno.objects.exists())

    def test_documento_valido_fica_guardado_no_aluno(self):
        self.enviar('cadastro_aluno', documento=self.documento_valido('rg.png', b'\x89PNG\r\n\x1a\n teste'))
        aluno = Aluno.objects.get(matricula='2024001')
        self.assertTrue(aluno.documento_confirmacao.name.endswith('rg.png'))
        self.assertTrue(aluno.documento_confirmacao.storage.exists(aluno.documento_confirmacao.name))
        self.assertIsNotNone(aluno.cadastrado_em)

    def test_formulario_de_aluno_e_de_monitor_pedem_documento(self):
        for rota in ('cadastro_aluno', 'cadastro_monitor'):
            with self.subTest(rota):
                r = self.client.get(reverse(rota))
                self.assertContains(r, 'type="file"')
                self.assertContains(r, 'enctype="multipart/form-data"')

    def test_monitor_sem_documento_e_recusado(self):
        r = self.client.post(reverse('cadastro_monitor'), {'matricula': '2024001', 'nome': 'Ana', 'senha': 'abc123'})
        self.assertContains(r, 'Envie o documento de confirmação')
        self.assertFalse(Monitor.objects.exists())


class AlunoAguardandoAprovacaoTests(TestCase):
    """Aluno que se cadastrou e ainda não foi aprovado pelo administrador não consegue entrar."""

    def setUp(self):
        pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, pasta, True)
        override = override_settings(MEDIA_ROOT=pasta)
        override.enable()
        self.addCleanup(override.disable)

    def test_login_bloqueado_ate_aprovacao_e_liberado_depois(self):
        aluno = Aluno.objects.create(matricula='a1', nome='Ana', senha=make_password('segredo'), aprovado=False)

        r = self.client.post(reverse('home'), {'tipo': 'aluno', 'username': 'a1', 'password': 'segredo'})
        self.assertContains(r, 'Seu cadastro ainda está aguardando a aprovação')
        self.assertNotIn('aluno_id', self.client.session)

        aluno.aprovado = True
        aluno.save()
        r = self.client.post(reverse('home'), {'tipo': 'aluno', 'username': 'a1', 'password': 'segredo'})
        self.assertRedirects(r, reverse('painel'), fetch_redirect_response=False)
        self.assertEqual(self.client.session.get('aluno_id'), aluno.id)

    def test_senha_errada_continua_com_a_mensagem_de_senha(self):
        Aluno.objects.create(matricula='a1', nome='Ana', senha=make_password('segredo'), aprovado=False)
        r = self.client.post(reverse('home'), {'tipo': 'aluno', 'username': 'a1', 'password': 'errada'})
        self.assertContains(r, 'Senha incorreta.')


class LoginTests(TestCase):
    def setUp(self):
        Aluno.objects.create(matricula='a1', nome='Ana', senha=make_password('segredo'))

    def test_pagina_inicial_tem_login_e_links_de_cadastro(self):
        r = self.client.get(reverse('home'))
        self.assertContains(r, 'Entrar como')
        self.assertContains(r, f'href="{reverse("cadastro_aluno")}"')
        self.assertContains(r, f'href="{reverse("cadastro_monitor")}"')
        self.assertContains(r, 'value="aluno" checked')

    def test_erro_de_login_mantem_matricula_e_papel(self):
        r = self.client.post(reverse('home'), {'tipo': 'monitor', 'username': 'a1', 'password': 'x'})
        self.assertContains(r, 'Matrícula não encontrada')
        self.assertContains(r, 'value="a1"')
        self.assertContains(r, 'value="monitor" checked')

    def test_login_com_campo_faltando_nao_da_erro_500(self):
        r = self.client.post(reverse('home'), {'tipo': 'aluno'})
        self.assertEqual(r.status_code, 200)
