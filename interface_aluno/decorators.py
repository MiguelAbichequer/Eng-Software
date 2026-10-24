from functools import wraps

from django.shortcuts import redirect

from alunos.models import Aluno


#protege as telas que só podem ser acessadas depois do login
#o login (inicio/views.py) guarda o id do aluno na sessão; aqui conferimos se ele existe
def aluno_logado(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        aluno_id = request.session.get('aluno_id')
        if not aluno_id:
            return redirect('home')

        try:
            request.aluno = Aluno.objects.get(pk=aluno_id)
        except Aluno.DoesNotExist:
            #aluno apagado depois do login: limpa a sessão e volta para a tela inicial
            request.session.flush()
            return redirect('home')

        return view(request, *args, **kwargs)

    return wrapper