from django.shortcuts import render
from django.contrib.auth.hashers import check_password
from alunos.models import Aluno

# Create your views here.

from django.shortcuts import render
from django.contrib.auth.hashers import check_password
from alunos.models import Aluno


def home(request):
    if request.method == 'POST':
        matricula = request.POST['username']
        senha = request.POST['password']

        try:
            aluno = Aluno.objects.get(matricula=matricula)

            if check_password(senha, aluno.senha):
                return render(request, 'inicio/home.html', {
                    'mensagem': 'Login realizado com sucesso!'
                })
            else:
                return render(request, 'inicio/home.html', {
                    'erro': 'Senha incorreta.'
                })

        except Aluno.DoesNotExist:
            return render(request, 'inicio/home.html', {
                'erro': 'Matrícula não encontrada.'
            })

    return render(request, 'inicio/home.html')
