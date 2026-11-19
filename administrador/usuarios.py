"""
Consulta e expulsão de usuários (alunos e monitores) pelo administrador.

Expulsar NÃO apaga a conta. Apagar levaria junto, em cascata, todas as solicitações da
pessoa, e o relatório de atendimentos perderia o histórico. Em vez disso, a conta recebe
a data da expulsão (expulso_em), o que:

- impede o login (inicio/views.py) e derruba a sessão aberta (decorators de cada interface);
- esconde o monitor expulso da lista e da página de monitores dos alunos;
- cancela os atendimentos que ainda não começaram, liberando os horários.

Readmitir apenas limpa a data: a pessoa volta a entrar. Os atendimentos cancelados não voltam.
"""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404

from alunos.models import Aluno
from alunos.disponibilidade import ja_terminou, pode_cancelar
from monitor.models import Monitor, Solicitacao

#tipos de usuário que o administrador consulta, como aparecem na URL
TIPOS = {'aluno': Aluno, 'monitor': Monitor}

#quantos atendimentos passados aparecem na página de um usuário
LIMITE_HISTORICO = 20


def modelo_do_tipo(tipo):
    """'aluno' -> Aluno, 'monitor' -> Monitor; qualquer outro valor vira 404."""
    try:
        return TIPOS[tipo]
    except KeyError:
        raise Http404('Tipo de usuário inválido.')


def solicitacoes_de(usuario):
    """Todas as solicitações ligadas ao usuário: as que o aluno fez ou as que o monitor recebeu."""
    if isinstance(usuario, Monitor):
        filtro = Q(horario__monitor=usuario)
    else:
        filtro = Q(aluno=usuario)
    return Solicitacao.objects.filter(filtro).select_related('aluno', 'horario__monitor')


def separar(solicitacoes, agora):
    """Divide em (próximas, anteriores): próximas em ordem de data, anteriores das mais recentes."""
    proximas, anteriores = [], []
    for s in solicitacoes:
        (anteriores if ja_terminou(s, agora) else proximas).append(s)
    ordem = lambda s: (s.data, s.hora_inicio)
    proximas.sort(key=ordem)
    anteriores.sort(key=ordem, reverse=True)
    return proximas, anteriores


def canceladas_ao_expulsar(usuario, agora):
    """Os atendimentos que a expulsão cancela: os que ainda não começaram."""
    return [
        s for s in solicitacoes_de(usuario).filter(data__gte=agora.date())
        if pode_cancelar(s, agora)
    ]


def expulsar(usuario, motivo, agora):
    """Bloqueia a conta e cancela os atendimentos futuros. Devolve quantos foram cancelados."""
    with transaction.atomic():
        canceladas = canceladas_ao_expulsar(usuario, agora)
        Solicitacao.objects.filter(pk__in=[s.pk for s in canceladas]).delete()

        usuario.expulso_em = agora
        usuario.motivo_expulsao = motivo
        campos = ['expulso_em', 'motivo_expulsao']
        if isinstance(usuario, Monitor):
            #quem foi expulso não está atendendo
            usuario.status = Monitor.INDISPONIVEL
            campos.append('status')
        usuario.save(update_fields=campos)
    return len(canceladas)


def readmitir(usuario):
    """Desfaz a expulsão: a pessoa volta a conseguir entrar."""
    usuario.expulso_em = None
    usuario.motivo_expulsao = ''
    usuario.save(update_fields=['expulso_em', 'motivo_expulsao'])


@dataclass
class Linha:
    """Uma linha da lista de usuários (aluno ou monitor)."""
    tipo: str
    usuario: object
    solicitacoes: int

    @property
    def tipo_rotulo(self):
        return 'Aluno' if self.tipo == 'aluno' else 'Monitor'


def listar(busca='', tipo='', situacao=''):
    """
    Alunos e monitores numa lista só, em ordem de nome.

    A mesma pessoa pode aparecer duas vezes (uma como aluno e outra como monitor),
    porque são cadastros separados, cada um com seu login.
    """
    filtro = Q()
    if busca:
        filtro = Q(nome__icontains=busca) | Q(matricula__icontains=busca)
    if situacao == 'ativos':
        filtro &= Q(expulso_em__isnull=True)
    elif situacao == 'expulsos':
        filtro &= Q(expulso_em__isnull=False)

    linhas = []
    if tipo in ('', 'aluno'):
        #Count('solicitacoes') vira um COUNT com JOIN e GROUP BY no SQL
        for a in Aluno.objects.filter(filtro).annotate(total=Count('solicitacoes')):
            linhas.append(Linha('aluno', a, a.total))
    if tipo in ('', 'monitor'):
        #para o monitor, as solicitações chegam através dos horários dele
        for m in Monitor.objects.filter(filtro).annotate(total=Count('horarios__solicitacoes')):
            linhas.append(Linha('monitor', m, m.total))

    linhas.sort(key=lambda l: (l.usuario.nome.casefold(), l.tipo))
    return linhas
