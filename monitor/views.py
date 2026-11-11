from django.contrib.auth.hashers import make_password
from django.shortcuts import render
from .models import Monitor


def cadastro(request):
    if request.method == 'POST':
        matricula = request.POST['matricula']
        nome = request.POST['nome']
        senha = request.POST['senha']

        monitor = Monitor(
            matricula=matricula,
            nome=nome,
            senha=make_password(senha)
        )

        monitor.save()

    return render(request, 'monitor/cadastro.html')
