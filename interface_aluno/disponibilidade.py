"""
Regras de disponibilidade dos monitores.

O estado do monitor ("disponível agora", "em atendimento" ou "indisponível") e as vagas
livres são calculados na hora, a partir dos horários semanais do monitor e das solicitações
já feitas. A única coisa guardada é o status manual temporário (Monitor.status_manual), que
o monitor pode usar para sobrepor o estado calculado.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone

from monitor.models import Solicitacao

#quantas semanas à frente o aluno pode solicitar horários
JANELA_SEMANAS = 2

DISPONIVEL = 'disponivel'
EM_ATENDIMENTO = 'em_atendimento'
INDISPONIVEL = 'indisponivel'


@dataclass
class Vaga:
    horario: object
    data: date


@dataclass
class Resumo:
    monitor: object
    estado: str = INDISPONIVEL
    horario_atual: object = None   #horário em andamento agora, se houver
    vagas: list = field(default_factory=list)
    estado_automatico: str = INDISPONIVEL  #o que os horários dizem, sem o status manual
    manual: bool = False           #o estado mostrado vem do status manual do monitor?
    manual_ate: object = None      #até quando o status manual vale (hora local)

    @property
    def proxima_vaga(self):
        return self.vagas[0] if self.vagas else None

    @property
    def disponivel_ate(self):
        """Até que horas o monitor segue disponível (só faz sentido quando o estado é disponível)."""
        if self.manual and self.manual_ate:
            return self.manual_ate.time()
        return self.horario_atual.hora_fim if self.horario_atual else None


def agora_local():
    #usa o fuso configurado em settings.TIME_ZONE
    return timezone.localtime()


def datas_ocupadas(monitores, a_partir_de):
    """Retorna {(id_do_horario, data): id_do_aluno} das solicitações já feitas."""
    solicitacoes = Solicitacao.objects.filter(
        horario__monitor__in=monitores,
        data__gte=a_partir_de,
    ).values_list('horario_id', 'data', 'aluno_id')
    return {(horario_id, data): aluno_id for horario_id, data, aluno_id in solicitacoes}


def datas_da_janela(horario, agora):
    """Datas em que o horário ainda pode ser solicitado (ignora as já reservadas)."""
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


def status_manual_vigente(monitor, agora):
    """O status que o monitor definiu à mão, se ainda não expirou; senão ''."""
    if monitor.status_manual and monitor.status_manual_ate and monitor.status_manual_ate > agora:
        return monitor.status_manual
    return ''


def resumir_monitor(monitor, ocupados, agora):
    """Calcula o estado atual e as vagas livres de um monitor."""
    resumo = Resumo(monitor=monitor)
    hoje = agora.date()
    hora = agora.time()

    for horario in monitor.horarios.all():
        #estado atual: algum horário do monitor está acontecendo agora?
        if horario.dia_semana == hoje.weekday() and horario.hora_inicio <= hora < horario.hora_fim:
            resumo.horario_atual = horario
            resumo.estado = EM_ATENDIMENTO if (horario.id, hoje) in ocupados else DISPONIVEL

        for data in datas_da_janela(horario, agora):
            if (horario.id, data) not in ocupados:
                resumo.vagas.append(Vaga(horario=horario, data=data))

    resumo.vagas.sort(key=lambda vaga: (vaga.data, vaga.horario.hora_inicio))

    #o status manual sobrepõe o calculado, com uma exceção: "disponível" não passa por cima de
    #um atendimento solicitado (o monitor está ocupado com um aluno de verdade)
    resumo.estado_automatico = resumo.estado
    manual = status_manual_vigente(monitor, agora)
    if manual == INDISPONIVEL or (manual == DISPONIVEL and resumo.estado == INDISPONIVEL):
        resumo.estado = manual
        resumo.manual = True
        resumo.manual_ate = timezone.localtime(monitor.status_manual_ate)
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