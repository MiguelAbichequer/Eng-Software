from django.shortcuts import render
from .models import Monitor


def cadastro(request):
    if request.method == 'POST':
        matricula = request.POST['matricula']
        nome = request.POST['nome']

        monitor = Monitor(
            matricula=matricula,
            nome=nome
        )

        monitor.save()

    return render(request, 'monitor/cadastro.html')
