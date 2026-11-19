"""
Reserva de blocos de 15 minutos.

O aluno escolhe um horário numa data e marca os blocos que quer. Os blocos seguidos
viram uma solicitação só (14:00 + 14:15 + 14:30 = uma solicitação das 14:00 às 14:45);
blocos separados viram solicitações diferentes (14:00 e 15:00 = duas solicitações).

Duas regras protegem as reservas:
- cada bloco é de um aluno só;
- cada aluno reserva no máximo LIMITE_BLOCOS_POR_DIA blocos por dia com o mesmo monitor.

Para a primeira valer mesmo com dois alunos clicando no mesmo instante, a reserva trava a
linha do horário no banco (select_for_update) antes de conferir e gravar. Enquanto um aluno
está reservando, o outro espera; quando chega a vez dele, já vê o bloco ocupado.
"""

from datetime import time

from django.db import transaction

from monitor.models import MINUTOS_BLOCO, Horario, Solicitacao

from .disponibilidade import (
    LIVRE, blocos_ocupados, datas_da_janela, inicios_dos_blocos, montar_blocos, somar_minutos,
)

#quantos blocos (de 15 minutos) um aluno pode ter por dia com o mesmo monitor: 4 = 1 hora
LIMITE_BLOCOS_POR_DIA = 4


class ReservaRecusada(Exception):
    """A reserva não pode ser feita. A mensagem explica o motivo para o aluno."""


def ler_horas(textos):
    """['14:00', '14:15'] -> [time(14, 0), time(14, 15)], sem repetidas e em ordem. Ignora lixo."""
    horas = set()
    for texto in textos:
        try:
            horas.add(time.fromisoformat(texto))
        except ValueError:
            continue
    return sorted(horas)


def agrupar_seguidas(inicios):
    """
    Junta os blocos seguidos em trechos (início, fim).

    [14:00, 14:15, 15:00] -> [(14:00, 14:30), (15:00, 15:15)]
    """
    trechos = []
    for inicio in inicios:
        fim = somar_minutos(inicio, MINUTOS_BLOCO)
        if trechos and trechos[-1][1] == inicio:
            trechos[-1] = (trechos[-1][0], fim)  #encosta no trecho anterior: estende
        else:
            trechos.append((inicio, fim))
    return trechos


def blocos_por_dia(aluno, monitor, a_partir_de):
    """{data: quantos blocos o aluno tem com este monitor nessa data}, de a_partir_de em diante."""
    contagem = {}
    reservas = Solicitacao.objects.filter(aluno=aluno, horario__monitor=monitor, data__gte=a_partir_de)
    for s in reservas:
        contagem[s.data] = contagem.get(s.data, 0) + len(inicios_dos_blocos(s.hora_inicio, s.hora_fim))
    return contagem


def reservar(aluno, horario, data, inicios, assunto, formato, participantes, agora):
    """
    Grava os blocos escolhidos e devolve a lista de solicitações criadas.
    Levanta ReservaRecusada se alguma regra não for cumprida (nesse caso nada é gravado).
    """
    if not inicios:
        raise ReservaRecusada('Marque pelo menos um horário.')
    if data not in datas_da_janela(horario, agora):
        raise ReservaRecusada('Essa data não está mais disponível para solicitação.')

    with transaction.atomic():
        #trava o horário até o fim do bloco: outra reserva nele espera esta terminar
        horario = Horario.objects.select_for_update().get(pk=horario.pk)

        #a situação de cada bloco agora, já com as reservas de todo mundo
        ocupados = blocos_ocupados([horario.monitor_id], data)
        situacao = {c.inicio: c.situacao for c in montar_blocos(horario, data, ocupados, agora, aluno.id)}

        for inicio in inicios:
            if inicio not in situacao:
                raise ReservaRecusada('Um dos horários escolhidos não faz parte deste atendimento.')
            if situacao[inicio] != LIVRE:
                raise ReservaRecusada(
                    f'O horário das {inicio:%H:%M} não está mais livre. '
                    'Alguém pode ter acabado de reservá-lo; escolha outro.'
                )

        ja_tem = blocos_por_dia(aluno, horario.monitor_id, data).get(data, 0)
        if ja_tem + len(inicios) > LIMITE_BLOCOS_POR_DIA:
            restam = max(LIMITE_BLOCOS_POR_DIA - ja_tem, 0)
            raise ReservaRecusada(
                f'Cada aluno pode reservar até {LIMITE_BLOCOS_POR_DIA} horários de {MINUTOS_BLOCO} minutos '
                f'por dia com o mesmo monitor ({LIMITE_BLOCOS_POR_DIA * MINUTOS_BLOCO} minutos no total). '
                f'Você ainda pode reservar {restam} nesse dia.'
            )

        return [
            Solicitacao.objects.create(
                aluno=aluno, horario=horario, data=data, hora_inicio=inicio, hora_fim=fim,
                assunto=assunto, formato=formato, participantes=participantes,
            )
            for inicio, fim in agrupar_seguidas(inicios)
        ]
