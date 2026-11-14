"""
Regras de disponibilidade dos monitores.

Estado do monitor ("disponível", "em atendimento" ou "indisponível"): é o próprio monitor
quem escolhe, no painel dele (Monitor.status). Não é calculado pelos horários.

Vagas: calculadas na hora, a partir dos horários semanais do monitor e das solicitações
já feitas.

Um mesmo horário pode ser solicitado por vários alunos na mesma data (a monitoria funciona
como um encontro aberto). Por isso um horário reservado continua aparecendo como vaga, com
a contagem de quantos alunos já reservaram.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone

from monitor.models import Monitor, Solicitacao

#quantas semanas à frente o aluno pode solicitar horários
JANELA_SEMANAS = 2

DISPONIVEL = Monitor.DISPONIVEL
EM_ATENDIMENTO = Monitor.EM_ATENDIMENTO
INDISPONIVEL = Monitor.INDISPONIVEL


@dataclass
class Vaga:
    horario: object
    data: date
    inscritos: int = 0    #quantos alunos já reservaram este horário nesta data
    minha: bool = False   #o aluno que está vendo já reservou? (preenchido pela view)


@dataclass
class Resumo:
    monitor: object
    estado: str = INDISPONIVEL
    vagas: list = field(default_factory=list)

    @property
    def proxima_vaga(self):
        return self.vagas[0] if self.vagas else None


def agora_local():
    #usa o fuso configurado em settings.TIME_ZONE
    return timezone.localtime()


def datas_ocupadas(monitores, a_partir_de):
    """
    Retorna {(id_do_horario, data): {ids dos alunos}} das solicitações já feitas.

    Exemplo: {(7, date(2026, 11, 17)): {3, 5}} = o horário 7 no dia 17/11 tem os alunos 3 e 5.
    Uma única consulta ao banco; depois, saber quem reservou é só olhar no dicionário.
    """
    solicitacoes = Solicitacao.objects.filter(
        horario__monitor__in=monitores,
        data__gte=a_partir_de,
    ).values_list('horario_id', 'data', 'aluno_id')

    ocupados = {}
    for horario_id, data, aluno_id in solicitacoes:
        ocupados.setdefault((horario_id, data), set()).add(aluno_id)
    return ocupados


def datas_da_janela(horario, agora):
    """Datas em que o horário ainda pode ser solicitado, dentro da janela de semanas."""
    hoje = agora.date()
    dias_ate_proxima = (horario.dia_semana - hoje.weekday()) % 7
    primeira = hoje + timedelta(days=dias_ate_proxima)

    datas = []
    for semana in range(JANELA_SEMANAS):
        data = primeira + timedelta(weeks=semana)
        #horário de hoje que já terminou não pode mais ser solicitado
        if data == hoje and agora.time() >= horario.hora_fim:
            continue
        datas.append(data)
    return datas


def resumir_monitor(monitor, ocupados, agora):
    """O estado atual (escolhido pelo monitor) e as vagas de um monitor."""
    resumo = Resumo(monitor=monitor, estado=monitor.status)

    for horario in monitor.horarios.all():
        #todas as datas da janela viram vagas, reservadas ou não: o horário não "lota"
        for data in datas_da_janela(horario, agora):
            inscritos = len(ocupados.get((horario.id, data), ()))
            resumo.vagas.append(Vaga(horario=horario, data=data, inscritos=inscritos))

    resumo.vagas.sort(key=lambda vaga: (vaga.data, vaga.horario.hora_inicio))
    return resumo


def ja_comecou(solicitacao, agora):
    """O atendimento já começou (ou já passou)?"""
    return (solicitacao.data, solicitacao.horario.hora_inicio) <= (agora.date(), agora.time())


def ja_terminou(solicitacao, agora):
    """O atendimento já acabou?"""
    return (solicitacao.data, solicitacao.horario.hora_fim) <= (agora.date(), agora.time())


def pode_cancelar(solicitacao, agora):
    """O aluno só pode cancelar antes de o atendimento começar."""
    return not ja_comecou(solicitacao, agora)