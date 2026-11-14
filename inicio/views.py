from django.shortcuts import redirect, render
from django.contrib.auth.hashers import check_password
from django.views.decorators.http import require_POST
from alunos.models import Aluno
from monitor.models import Monitor

CONTA_SUSPENSA = 'Esta conta foi suspensa pela administração. Procure a coordenação da monitoria.'


def _entrar(request, chave, usuario, destino):
    #guarda quem fez login na sessão e leva a pessoa para a tela de utilização
    request.session.cycle_key()  #novo id de sessão a cada login
    request.session.pop('aluno_id', None)  #a sessão é de aluno ou de monitor, nunca dos dois
    request.session.pop('monitor_id', None)
    request.session[chave] = usuario.id
    return redirect(destino)


def home(request):
    if request.method == 'POST':
        matricula = request.POST.get('username', '').strip()
        senha = request.POST.get('password', '')
        #um monitor também costuma ser aluno (mesma matrícula nas duas tabelas),
        #por isso o login pergunta em qual papel a pessoa quer entrar
        tipo = 'monitor' if request.POST.get('tipo') == 'monitor' else 'aluno'
        modelo = Monitor if tipo == 'monitor' else Aluno
        #em caso de erro, a tela volta com o papel e a matrícula preenchidos
        contexto = {'tipo': tipo, 'matricula': matricula}

        try:
            usuario = modelo.objects.get(matricula=matricula)

            if check_password(senha, usuario.senha):
                #conta expulsa pelo administrador: a senha está certa, mas o acesso foi bloqueado
                #(só avisamos depois de conferir a senha, para não revelar a situação a qualquer um)
                if usuario.expulso:
                    return render(request, 'inicio/home.html', {**contexto, 'erro': CONTA_SUSPENSA})
                if tipo == 'monitor':
                    return _entrar(request, 'monitor_id', usuario, 'monitor_painel')
                return _entrar(request, 'aluno_id', usuario, 'painel')
            else:
                return render(request, 'inicio/home.html', {**contexto, 'erro': 'Senha incorreta.'})

        except modelo.DoesNotExist:
            return render(request, 'inicio/home.html', {**contexto, 'erro': 'Matrícula não encontrada.'})

    #quem já está logado vai direto para a sua tela
    if request.session.get('aluno_id'):
        return redirect('painel')
    if request.session.get('monitor_id'):
        return redirect('monitor_painel')

    #?tipo=monitor (vindo do cadastro) deixa "Monitor" já marcado no login
    contexto = {'tipo': 'monitor' if request.GET.get('tipo') == 'monitor' else 'aluno'}

    #os decorators mandam para cá com ?suspenso=1 quem foi expulso com a sessão aberta
    if request.GET.get('suspenso'):
        contexto['erro'] = CONTA_SUSPENSA

    return render(request, 'inicio/home.html', contexto)


@require_POST
def sair(request):
    #monitor saindo: o status volta para "indisponível", para os alunos não o verem
    #disponível depois que ele foi embora
    monitor_id = request.session.get('monitor_id')
    if monitor_id:
        Monitor.objects.filter(pk=monitor_id).update(status=Monitor.INDISPONIVEL)
    request.session.flush()
    return redirect('home')
