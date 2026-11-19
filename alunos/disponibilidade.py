"""
Regras de disponibilidade dos monitores.

Estado do monitor ("disponível", "em atendimento" ou "indisponível"): é o próprio monitor
quem escolhe, no painel dele (Monitor.status). Não é calculado pelos horários.

Vagas: cada horário semanal do monitor (ex.: segunda, 14:00-16:00), em cada data das
próximas semanas, é dividido em blocos de 15 minutos (14:00, 14:15, ..., 15:45).
Cada bloco pode ser reservado por um aluno só; depois disso fica cinza para os outros.
Nada disso é gravado: os blocos são calculados na hora a partir das solicitações.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from monitor.models import MINUTOS_BLOCO, Monitor, Solicitacao

#quantas semanas à frente o aluno pode solicitar horários
JANELA_SEMANAS = 2

DISPONIVEL = Monitor.DISPONIVEL
EM_ATENDIMENTO = Monitor.EM_ATENDIMENTO
INDISPONIVEL = Monitor.INDISPONIVEL

#situações de um bloco (usadas também como classe CSS na tela)
LIVRE = 'livre'
MEU = 'meu'            #reservado pelo aluno que está vendo
OCUPADO = 'ocupado'    #reservado por outro aluno
PASSOU = 'passou'      #já começou ou já passou


@dataclass
class Bloco:
    inicio: time
    fim: time
    situacao: str = LIVRE

    @property
    def livre(self):
        return self.situacao == LIVRE


@dataclass
class Vaga:
    """Um horário semanal numa data concreta, já dividido em blocos."""
    horario: object
    data: date
    blocos: list = field(default_factory=list)

    @property
    def livres(self):
        return [c for c in self.blocos if c.livre]

    @property
    def meus(self):
        return [c for c in self.blocos if c.situacao == MEU]


@dataclass
class Resumo:
    monitor: object
    estado: str = INDISPONIVEL
    vagas: list = field(default_factory=list)

    @property
    def vagas_com_livres(self):
        return [v for v in self.vagas if v.livres]

    @property
    def proxima_vaga(self):
        """A primeira data/horário que ainda tem bloco livre."""
        livres = self.vagas_com_livres
        return livres[0] if livres else None

    @property
    def proximo_bloco(self):
        vaga = self.proxima_vaga
        return vaga.livres[0] if vaga else None


def agora_local():
    #usa o fuso configurado em settings.TIME_ZONE
    return timezone.localtime()


def somar_minutos(hora, minutos):
    """time + minutos. (O Python não soma timedelta direto em time, então passa por datetime.)"""
    return (datetime.combine(date.min, hora) + timedelta(minutes=minutos)).time()


def inicios_dos_blocos(hora_inicio, hora_fim):
    """[14:00, 14:15, 14:30, 14:45] para o trecho 14:00-15:00."""
    inicios = []
    atual = hora_inicio
    #o bloco só entra se couber inteira antes do fim
    while somar_minutos(atual, MINUTOS_BLOCO) <= hora_fim and atual < hora_fim:
        inicios.append(atual)
        proxima = somar_minutos(atual, MINUTOS_BLOCO)
        if proxima <= atual:  #passou da meia-noite: para aqui
            break
        atual = proxima
    return inicios


def blocos_ocupados(monitores, a_partir_de):
    """
    Retorna {(id_do_horario, data): {início_da_bloco: id_do_aluno}}.

    Exemplo: {(7, date(2026, 11, 17)): {time(14, 0): 3, time(14, 15): 3}} = no horário 7
    do dia 17/11, os blocos das 14:00 e das 14:15 são do aluno 3.
    Uma única consulta ao banco; depois, saber quem reservou é só olhar no dicionário.
    """
    solicitacoes = Solicitacao.objects.filter(
        horario__monitor__in=monitores,
        data__gte=a_partir_de,
    ).values_list('horario_id', 'data', 'hora_inicio', 'hora_fim', 'aluno_id')

    ocupados = {}
    for horario_id, data, inicio, fim, aluno_id in solicitacoes:
        do_horario = ocupados.setdefault((horario_id, data), {})
        for bloco in inicios_dos_blocos(inicio, fim):
            do_horario[bloco] = aluno_id
    return ocupados


def datas_da_janela(horario, agora):
    """Datas em que o horário ainda pode ser solicitado, dentro da janela de semanas."""
    hoje = agora.date()
    dias_ate_proxima = (horario.dia_semana - hoje.weekday()) % 7
    primeira = hoje + timedelta(days=dias_ate_proxima)

    datas = []
    for semana in range(JANELA_SEMANAS):
        data = primeira + timedelta(weeks=semana)
        #horário de hoje que já terminou não aparece mais
        if data == hoje and agora.time() >= horario.hora_fim:
            continue
        datas.append(data)
    return datas


def montar_blocos(horario, data, ocupados, agora, aluno_id=None):
    """Os blocos de um horário numa data, cada uma com a sua situação."""
    do_horario = ocupados.get((horario.id, data), {})
    blocos = []
    for inicio in inicios_dos_blocos(horario.hora_inicio, horario.hora_fim):
        dono = do_horario.get(inicio)
        if dono is not None:
            situacao = MEU if dono == aluno_id else OCUPADO
        elif (data, inicio) <= (agora.date(), agora.time()):
            situacao = PASSOU  #o bloco já começou: não dá mais para reservar
        else:
            situacao = LIVRE
        blocos.append(Bloco(inicio, somar_minutos(inicio, MINUTOS_BLOCO), situacao))
    return blocos


def resumir_monitor(monitor, ocupados, agora, aluno_id=None):
    """
    Estado atual e vagas de um monitor.

    aluno_id: quem está vendo a tela. Os blocos dele aparecem como "meu", e os dos
    outros alunos como "ocupado".
    """
    resumo = Resumo(monitor=monitor, estado=monitor.status)
    for horario in monitor.horarios.all():
        for data in datas_da_janela(horario, agora):
            blocos = montar_blocos(horario, data, ocupados, agora, aluno_id)
            resumo.vagas.append(Vaga(horario=horario, data=data, blocos=blocos))

    resumo.vagas.sort(key=lambda vaga: (vaga.data, vaga.horario.hora_inicio))
    return resumo


def ja_comecou(solicitacao, agora):
    """O atendimento já começou (ou já passou)?"""
    return (solicitacao.data, solicitacao.hora_inicio) <= (agora.date(), agora.time())


def ja_terminou(solicitacao, agora):
    """O atendimento já acabou?"""
    return (solicitacao.data, solicitacao.hora_fim) <= (agora.date(), agora.time())


def pode_cancelar(solicitacao, agora):
    """O aluno só pode cancelar antes de o atendimento começar."""
    return not ja_comecou(solicitacao, agora)
