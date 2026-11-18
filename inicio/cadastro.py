"""
Cadastro de aluno e de monitor.

Os dois cadastros pedem as mesmas coisas (matrícula, nome e senha), então a regra fica
num lugar só e cada app só diz qual modelo usar (alunos/views.py e monitor/views.py).

O aluno também envia um documento de confirmação (exige_documento=True). A conta nasce
bloqueada até o administrador conferir o documento e aprovar o cadastro.

Depois de cadastrar, a pessoa volta para a página inicial com uma mensagem de confirmação
e com o papel certo (aluno ou monitor) já marcado no login.
"""

import os

from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse

#os mesmos limites dos campos nos modelos (CharField max_length)
MAX_MATRICULA = 20
MAX_NOME = 100

#documento de confirmação: tipos aceitos e tamanho máximo
EXTENSOES_DOCUMENTO = ('.pdf', '.jpg', '.jpeg', '.png')
MAX_BYTES_DOCUMENTO = 5 * 1024 * 1024  #5 MB

#primeiros bytes de cada formato: confere o conteúdo, não só o nome do arquivo
ASSINATURAS_DOCUMENTO = {
    '.pdf': (b'%PDF',),
    '.png': (b'\x89PNG',),
    '.jpg': (b'\xff\xd8\xff',),
    '.jpeg': (b'\xff\xd8\xff',),
}


def validar_documento(arquivo):
    """Devolve a mensagem de erro do documento, ou None se estiver tudo certo."""
    extensao = os.path.splitext(arquivo.name)[1].lower()
    if extensao not in EXTENSOES_DOCUMENTO:
        return 'O documento deve ser um arquivo PDF, JPG ou PNG.'
    if arquivo.size > MAX_BYTES_DOCUMENTO:
        return 'O documento pode ter no máximo 5 MB.'
    inicio = arquivo.read(8)
    arquivo.seek(0)
    if not any(inicio.startswith(assinatura) for assinatura in ASSINATURAS_DOCUMENTO[extensao]):
        return 'O arquivo enviado não parece ser um PDF, JPG ou PNG válido.'
    return None


def validar(modelo, matricula, nome, senha, documento=None, exige_documento=False):
    """Devolve a mensagem de erro, ou None se estiver tudo certo."""
    if not matricula or not nome or not senha:
        return 'Preencha matrícula, nome e senha.'
    if len(matricula) > MAX_MATRICULA:
        return f'A matrícula pode ter no máximo {MAX_MATRICULA} caracteres.'
    if len(nome) > MAX_NOME:
        return f'O nome pode ter no máximo {MAX_NOME} caracteres.'
    if modelo.objects.filter(matricula=matricula).exists():
        return 'Já existe um cadastro com essa matrícula. Se é você, é só entrar.'
    if exige_documento:
        if documento is None:
            return 'Envie o documento de confirmação para concluir o cadastro.'
        return validar_documento(documento)
    return None


def cadastrar(request, modelo, papel, precisa_aprovacao=False, exige_documento=False):
    """
    Mostra e processa o formulário de cadastro.

    modelo: Aluno ou Monitor.  papel: 'aluno' ou 'monitor' (usado nos textos e no login).
    precisa_aprovacao: a conta nasce bloqueada até o administrador aprovar.
    exige_documento: o formulário pede um documento de confirmação (aluno).
    """
    dados = {'matricula': '', 'nome': ''}
    erro = None

    if request.method == 'POST':
        #.get() em vez de ['...']: se um campo não vier, vira texto vazio em vez de erro 500
        matricula = request.POST.get('matricula', '').strip()
        nome = ' '.join(request.POST.get('nome', '').split())  #tira espaços sobrando
        senha = request.POST.get('senha', '')
        documento = request.FILES.get('documento') if exige_documento else None
        dados = {'matricula': matricula, 'nome': nome}

        erro = validar(modelo, matricula, nome, senha, documento, exige_documento)
        if erro is None:
            try:
                with transaction.atomic():
                    extras = {'aprovado': False} if precisa_aprovacao else {}
                    if exige_documento:
                        extras['documento_confirmacao'] = documento
                    modelo.objects.create(matricula=matricula, nome=nome, senha=make_password(senha), **extras)
            except IntegrityError:
                #outra pessoa cadastrou a mesma matrícula no mesmo instante
                erro = 'Já existe um cadastro com essa matrícula. Se é você, é só entrar.'

        if erro is None and precisa_aprovacao and exige_documento:
            messages.success(
                request,
                f'Cadastro enviado, {nome.split()[0]}! Um administrador vai conferir o seu documento '
                'de confirmação. Assim que ele aprovar, você poderá entrar com a sua matrícula e senha.',
            )
            return redirect(f"{reverse('home')}?tipo={papel}")

        if erro is None and precisa_aprovacao:
            messages.success(
                request,
                f'Cadastro enviado, {nome.split()[0]}! Um administrador precisa aprovar o seu cadastro '
                'de monitor antes de você conseguir entrar.',
            )
            return redirect(f"{reverse('home')}?tipo={papel}")

        if erro is None:
            messages.success(
                request,
                f'Cadastro feito, {nome.split()[0]}! Agora entre com a matrícula {matricula} e a sua senha.',
            )
            #?tipo=... deixa o papel certo marcado no formulário de login
            return redirect(f"{reverse('home')}?tipo={papel}")

    #em caso de erro, os campos voltam preenchidos (menos a senha e o arquivo)
    return render(request, 'inicio/cadastro.html', {
        'papel': papel,
        'dados': dados,
        'erro': erro,
        'exige_documento': exige_documento,
    })
