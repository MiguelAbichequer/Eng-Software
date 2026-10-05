from django.shortcuts import render
from django.contrib.auth.hashers import make_password
from .models import Aluno


def cadastro(request):
    if request.method == 'POST':
        matricula = request.POST['matricula']
        nome = request.POST['nome']
        senha = request.POST['senha']

        aluno = Aluno(
            matricula=matricula,
            nome=nome,
            senha=make_password(senha)
        )

        aluno.save()

    return render(request, 'alunos/cadastro.html')