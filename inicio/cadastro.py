"""
Cadastro de aluno e de monitor.

Os dois cadastros pedem as mesmas coisas (matrícula, nome e senha), então a regra fica
num lugar só e cada app só diz qual modelo usar (alunos/views.py e monitor/views.py).

Depois de cadastrar, a pessoa volta para a página inicial com uma mensagem de confirmação
e com o papel certo (aluno ou monitor) já marcado no login.
"""

from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.urls import reverse

#os mesmos limites dos campos nos modelos (CharField max_length)
MAX_MATRICULA = 20
MAX_NOME = 100


def validar(modelo, matricula, nome, senha):
    """Devolve a mensagem de erro, ou None se estiver tudo certo."""
    if not matricula or not nome or not senha:
        return 'Preencha matrícula, nome e senha.'
    if len(matricula) > MAX_MATRICULA:
        return f'A matrícula pode ter no máximo {MAX_MATRICULA} caracteres.'
    if len(nome) > MAX_NOME:
        return f'O nome pode ter no máximo {MAX_NOME} caracteres.'
    if modelo.objects.filter(matricula=matricula).exists():
        return 'Já existe um cadastro com essa matrícula. Se é você, é só entrar.'
    return None


def cadastrar(request, modelo, papel):
    """
    Mostra e processa o formulário de cadastro.

    modelo: Aluno ou Monitor.  papel: 'aluno' ou 'monitor' (usado nos textos e no login).
    """
    dados = {'matricula': '', 'nome': ''}
    erro = None

    if request.method == 'POST':
        #.get() em vez de ['...']: se um campo não vier, vira texto vazio em vez de erro 500
        matricula = request.POST.get('matricula', '').strip()
        nome = ' '.join(request.POST.get('nome', '').split())  #tira espaços sobrando
        senha = request.POST.get('senha', '')
        dados = {'matricula': matricula, 'nome': nome}

        erro = validar(modelo, matricula, nome, senha)
        if erro is None:
            try:
                with transaction.atomic():
                    modelo.objects.create(matricula=matricula, nome=nome, senha=make_password(senha))
            except IntegrityError:
                #outra pessoa cadastrou a mesma matrícula no mesmo instante
                erro = 'Já existe um cadastro com essa matrícula. Se é você, é só entrar.'

        if erro is None:
            messages.success(
                request,
                f'Cadastro feito, {nome.split()[0]}! Agora entre com a matrícula {matricula} e a sua senha.',
            )
            #?tipo=... deixa o papel certo marcado no formulário de login
            return redirect(f"{reverse('home')}?tipo={papel}")

    #em caso de erro, os campos voltam preenchidos (menos a senha)
    return render(request, 'inicio/cadastro.html', {
        'papel': papel,
        'dados': dados,
        'erro': erro,
    })
