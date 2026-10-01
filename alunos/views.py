from django.shortcuts import render
from .models import Aluno


def cadastro(request):
    if request.method == 'POST':
        matricula = request.POST['matricula']
        nome = request.POST['nome']

        aluno = Aluno(
            matricula=matricula,
            nome=nome
        )

        aluno.save()

    return render(request, 'alunos/cadastro.html')