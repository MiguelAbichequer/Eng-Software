from django.shortcuts import redirect, render
from django.contrib.auth.hashers import check_password
from django.views.decorators.http import require_POST
from alunos.models import Aluno
from monitor.models import Monitor


def _entrar(request, chave, usuario, destino):
    #guarda quem fez login na sessão e leva a pessoa para a tela de utilização
    request.session.cycle_key()  #novo id de sessão a cada login
    request.session.pop('aluno_id', None)  #a sessão é de aluno ou de monitor, nunca dos dois
    request.session.pop('monitor_id', None)
    request.session[chave] = usuario.id
    return redirect(destino)


def home(request):
    if request.method == 'POST':
        matricula = request.POST['username']
        senha = request.POST['password']
        #um monitor também costuma ser aluno (mesma matrícula nas duas tabelas),
        #por isso o login pergunta em qual papel a pessoa quer entrar
        tipo = request.POST.get('tipo', 'aluno')
        modelo = Monitor if tipo == 'monitor' else Aluno

        try:
            usuario = modelo.objects.get(matricula=matricula)

            if check_password(senha, usuario.senha):
                if tipo == 'monitor':
                    return _entrar(request, 'monitor_id', usuario, 'monitor_painel')
                return _entrar(request, 'aluno_id', usuario, 'painel')
            else:
                return render(request, 'inicio/home.html', {
                    'erro': 'Senha incorreta.',
                    'tipo': tipo,
                })

        except modelo.DoesNotExist:
            return render(request, 'inicio/home.html', {
                'erro': 'Matrícula não encontrada.',
                'tipo': tipo,
            })

    #quem já está logado vai direto para a sua tela
    if request.session.get('aluno_id'):
        return redirect('painel')
    if request.session.get('monitor_id'):
        return redirect('monitor_painel')

    return render(request, 'inicio/home.html')


@require_POST
def sair(request):
    request.session.flush()
    return redirect('home')