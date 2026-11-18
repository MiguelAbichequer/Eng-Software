"""
Divisão da janela de trabalho do monitor em blocos de atendimento.

O monitor informa quando trabalha (ex.: terça e quinta, das 13:30 às 15:00) e quanto dura
cada atendimento (ex.: 30 minutos). O sistema divide a janela em blocos seguidos, e cada bloco
vira um Horario que o aluno pode solicitar:

    13:30 - 14:00 | 14:00 - 14:30 | 14:30 - 15:00
"""

from datetime import date, datetime, timedelta

#durações que o monitor pode escolher para cada atendimento (em minutos)
DURACOES_ATENDIMENTO = (15, 30, 45, 60, 90, 120)
DURACAO_PADRAO = 30


def gerar_blocos(inicio, fim, duracao_minutos):
    """
    Divide [inicio, fim] em blocos de `duracao_minutos`. Retorna [(hora_inicio, hora_fim), ...].

    Só entram blocos completos: se sobrar um pedaço menor que a duração no fim da janela,
    ele é descartado (ex.: 13:30-15:00 com 60 min gera só 13:30-14:30; os 30 min finais
    não formam um atendimento inteiro). Lista vazia = a janela é menor que um atendimento.
    """
    passo = timedelta(minutes=duracao_minutos)
    #datetime.combine só serve para poder somar tempo às horas; a data é irrelevante
    atual = datetime.combine(date.min, inicio)
    limite = datetime.combine(date.min, fim)

    blocos = []
    while atual + passo <= limite:
        blocos.append((atual.time(), (atual + passo).time()))
        atual += passo
    return blocos
