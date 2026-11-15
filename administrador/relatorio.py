"""
Cálculos do relatório de atendimentos do administrador.

Tudo é calculado a partir da tabela de solicitações (monitor_solicitacao), filtrada
por período e, opcionalmente, por monitor.
"""

import calendar
from dataclasses import dataclass
from datetime import date

from django.db.models import Count, Q
from django.utils import timezone

from monitor.models import DiasSemana, Solicitacao

#quantas linhas aparecem na lista de "horários mais reservados"
LIMITE_RANKING = 10


@dataclass
class Periodo:
    inicio: date
    fim: date

    @property
    def dias(self):
        return (self.fim - self.inicio).days + 1


def periodo_padrao(hoje):
    """O mês corrente inteiro: do dia 1 ao último dia do mês."""
    ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]
    return Periodo(hoje.replace(day=1), hoje.replace(day=ultimo_dia))


def ler_periodo(inicio_txt, fim_txt, hoje):
    """
    Converte os textos do formulário ('2026-11-01') em um Periodo.

    Devolve (periodo, erro). Campos vazios usam o mês corrente; datas inválidas
    também, mas com uma mensagem de erro para a tela.
    """
    padrao = periodo_padrao(hoje)
    if not inicio_txt and not fim_txt:
        return padrao, None

    try:
        inicio = date.fromisoformat(inicio_txt) if inicio_txt else padrao.inicio
        fim = date.fromisoformat(fim_txt) if fim_txt else padrao.fim
    except ValueError:
        return padrao, 'Data inválida. Mostrando o mês atual.'

    if inicio > fim:
        return padrao, 'A data inicial deve ser antes da final. Mostrando o mês atual.'
    return Periodo(inicio, fim), None


def solicitacoes_do_periodo(periodo, monitor_id=None):
    """QuerySet base de todo o relatório."""
    qs = Solicitacao.objects.filter(data__range=(periodo.inicio, periodo.fim))
    if monitor_id:
        qs = qs.filter(horario__monitor_id=monitor_id)
    return qs


def ja_aconteceu(agora):
    """
    Filtro Q para "o atendimento já terminou": data passada, ou hoje com o horário encerrado.
    Mesma regra de interface_aluno.disponibilidade.ja_terminou, mas escrita para o banco.
    """
    hoje = agora.date()
    return Q(data__lt=hoje) | Q(data=hoje, hora_fim__lte=agora.time())


def resumo(qs, agora):
    """Números gerais do período, em uma única consulta (COUNT com FILTER)."""
    numeros = qs.aggregate(
        total=Count('id'),
        alunos=Count('aluno', distinct=True),
        realizadas=Count('id', filter=ja_aconteceu(agora)),
        online=Count('id', filter=Q(formato='online')),
        presencial=Count('id', filter=Q(formato='presencial')),
        individual=Count('id', filter=Q(participantes='individual')),
        grupo=Count('id', filter=Q(participantes='grupo')),
    )
    numeros['futuras'] = numeros['total'] - numeros['realizadas']
    return numeros


def por_dia(qs):
    """Solicitações e alunos distintos em cada data que teve pelo menos uma solicitação."""
    linhas = list(
        qs.values('data')
        .annotate(total=Count('id'), alunos=Count('aluno', distinct=True))
        .order_by('data')
    )
    #largura da barra na tela, em % do dia com mais solicitações
    maior = max((l['total'] for l in linhas), default=0)
    for linha in linhas:
        linha['barra'] = round(100 * linha['total'] / maior) if maior else 0
    return linhas

def horarios_mais_reservados(qs):
    """Os horários semanais (monitor + dia + hora) com mais solicitações no período."""
    linhas = list(
        qs.values(
            'horario_id', 'horario__monitor__nome', 'horario__dia_semana',
            'horario__hora_inicio', 'horario__hora_fim',
        )
        .annotate(total=Count('id'))
        .order_by('-total', 'horario__dia_semana', 'horario__hora_inicio')[:LIMITE_RANKING]
    )
    for linha in linhas:
        linha['dia'] = DiasSemana(linha['horario__dia_semana']).label
    return linhas


def por_monitor(qs):
    """Solicitações e alunos distintos de cada monitor no período."""
    return list(
        qs.values('horario__monitor_id', 'horario__monitor__nome')
        .annotate(total=Count('id'), alunos=Count('aluno', distinct=True))
        .order_by('-total', 'horario__monitor__nome')
    )


def montar(periodo, monitor_id=None, agora=None):
    """Junta todas as partes do relatório em um dicionário para o template."""
    agora = agora or timezone.localtime()
    qs = solicitacoes_do_periodo(periodo, monitor_id)
    return {
        'resumo': resumo(qs, agora),
        'por_dia': por_dia(qs),
        'horarios': horarios_mais_reservados(qs),
        'monitores': por_monitor(qs),
    }
