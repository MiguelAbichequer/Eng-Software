from functools import wraps

from django.shortcuts import redirect
from django.urls import reverse

from monitor.models import Monitor


#protege as telas que só podem ser acessadas por um monitor logado
#o login (inicio/views.py) guarda o id do monitor na sessão; aqui conferimos se ele existe
def monitor_logado(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        monitor_id = request.session.get('monitor_id')
        if not monitor_id:
            return redirect('home')

        try:
            request.monitor = Monitor.objects.prefetch_related('disciplinas').get(pk=monitor_id)
        except Monitor.DoesNotExist:
            #monitor apagado depois do login: limpa a sessão e volta para a tela inicial
            request.session.flush()
            return redirect('home')

        if request.monitor.expulso:
            #expulso pelo administrador com a sessão ainda aberta: desconecta na hora
            request.session.flush()
            return redirect(reverse('home') + '?suspenso=1')

        return view(request, *args, **kwargs)

    return wrapper
