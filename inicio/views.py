from django.shortcuts import redirect, render
from django.contrib.auth.hashers import check_password
from django.views.decorators.http import require_POST
from alunos.models import Aluno


def home(request):
    if request.method == 'POST':
        matricula = request.POST['username']
        senha = request.POST['password']

        try:
            aluno = Aluno.objects.get(matricula=matricula)

            if check_password(senha, aluno.senha):
                #guarda quem fez login na sessão e leva o aluno para a tela de utilização
                request.session.cycle_key()  #novo id de sessão a cada login
                request.session['aluno_id'] = aluno.id
                return redirect('painel')
            else:
                return render(request, 'inicio/home.html', {
                    'erro': 'Senha incorreta.'
                })

        except Aluno.DoesNotExist:
            return render(request, 'inicio/home.html', {
                'erro': 'Matrícula não encontrada.'
            })

    #quem já está logado vai direto para o painel
    if request.session.get('aluno_id'):
        return redirect('painel')

    return render(request, 'inicio/home.html')


@require_POST
def sair(request):
    request.session.flush()
    return redirect('home')