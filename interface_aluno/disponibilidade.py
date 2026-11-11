"""
Regras de disponibilidade dos monitores.

O estado do monitor ("disponível agora", "em atendimento" ou "indisponível") e as vagas
são calculados na hora, a partir dos horários semanais do monitor e das solicitações
já feitas.

Um mesmo horário pode ser solicitado por vários alunos na mesma data (a monitoria funciona
como um encontro aberto). Por isso um horário reservado continua aparecendo como vaga, com
a contagem de quantos alunos já reservaram. A única coisa guardada é o status manual temporário (Monitor.status_manual), que
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
    inscritos: int = 0    #quantos alunos já reservaram este horário nesta data
    minha: bool = False   #o aluno que está vendo já reservou? (preenchido pela view)


@dataclass
class Resumo:
    monitor: object
    estado: str = INDISPONIVEL
    horario_atual: object = None   #horário em andamento agora, se houver
    inscritos_atual: int = 0       #quantos alunos reservaram o horário em andamento
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


def status_manual_vigente(monitor, agora):
    """O status que o monitor definiu à mão, se ainda não expirou; senão ''."""
    if monitor.status_manual and monitor.status_manual_ate and monitor.status_manual_ate > agora:
        return monitor.status_manual
    return ''


def resumir_monitor(monitor, ocupados, agora):
    """Calcula o estado atual e as vagas de um monitor."""
    resumo = Resumo(monitor=monitor)
    hoje = agora.date()
    hora = agora.time()

    for horario in monitor.horarios.all():
        #estado atual: algum horário do monitor está acontecendo agora?
        if horario.dia_semana == hoje.weekday() and horario.hora_inicio <= hora < horario.hora_fim:
            resumo.horario_atual = horario
            resumo.inscritos_atual = len(ocupados.get((horario.id, hoje), ()))
            #com alguém reservado, o monitor está atendendo (e outros ainda podem entrar)
            resumo.estado = EM_ATENDIMENTO if resumo.inscritos_atual else DISPONIVEL

        #todas as datas da janela viram vagas, reservadas ou não: o horário não "lota"
        for data in datas_da_janela(horario, agora):
            inscritos = len(ocupados.get((horario.id, data), ()))
            resumo.vagas.append(Vaga(horario=horario, data=data, inscritos=inscritos))

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