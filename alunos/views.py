from datetime import date

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.formats import date_format
from django.views.decorators.http import require_POST

from inicio.cadastro import cadastrar
from monitor.models import MINUTOS_BLOCO, Disciplina, Horario, Monitor, Solicitacao

from .models import Aluno
from .decorators import aluno_logado
from .disponibilidade import (
    DISPONIVEL, EM_ATENDIMENTO, INDISPONIVEL,
    agora_local, blocos_ocupados, ja_comecou, ja_terminou, pode_cancelar, resumir_monitor,
)
from .reservas import LIMITE_BLOCOS_POR_DIA, ReservaRecusada, blocos_por_dia, ler_horas, reservar

#na lista, quem está disponível agora aparece primeiro
ORDEM_ESTADO = {DISPONIVEL: 0, EM_ATENDIMENTO: 1, INDISPONIVEL: 2}

#quantos atendimentos passados aparecem no histórico
LIMITE_HISTORICO = 20


def cadastro(request):
    #a regra do cadastro é a mesma do monitor: fica em inicio/cadastro.py
    #o aluno envia um documento de confirmação e só entra depois que o administrador aprovar
    return cadastrar(request, Aluno, 'aluno', precisa_aprovacao=True, exige_documento=True)


@aluno_logado
def painel(request):
    """Tela principal do aluno: lista de monitores com filtros."""
    nome = request.GET.get('nome', '').strip()
    disciplina_id = request.GET.get('disciplina', '')
    disponibilidade = request.GET.get('disponibilidade', '')

    #monitores expulsos ou ainda não aprovados pelo administrador não aparecem para os alunos
    monitores = Monitor.objects.filter(expulso_em__isnull=True, aprovado=True).prefetch_related('disciplinas', 'horarios')
    if nome:
        monitores = monitores.filter(nome__icontains=nome)
    if disciplina_id.isdigit():
        monitores = monitores.filter(disciplinas__id=int(disciplina_id))
    if disponibilidade == 'agora':
        #o status é escolhido pelo monitor e fica no banco, então dá para filtrar na consulta
        monitores = monitores.filter(status=DISPONIVEL)
    monitores = list(monitores.order_by('nome'))

    agora = agora_local()
    ocupados = blocos_ocupados(monitores, agora.date())
    resumos = [resumir_monitor(m, ocupados, agora, request.aluno.id) for m in monitores]

    #os blocos livres são calculados (não ficam no banco), então este filtro é aplicado aqui
    if disponibilidade == 'livres':
        resumos = [r for r in resumos if r.proxima_vaga]

    resumos.sort(key=lambda r: ORDEM_ESTADO[r.estado])  #sort é estável: mantém a ordem por nome

    return render(request, 'alunos/painel.html', {
        'aluno': request.aluno,
        'resumos': resumos,
        #só oferece no filtro as disciplinas que têm pelo menos um monitor ativo
        'disciplinas': Disciplina.objects.filter(
            monitores__isnull=False, monitores__expulso_em__isnull=True, monitores__aprovado=True,
        ).distinct(),
        'filtros': {'nome': nome, 'disciplina': disciplina_id, 'disponibilidade': disponibilidade},
        'filtrando': bool(nome or disciplina_id or disponibilidade),
        'querystring': request.GET.urlencode(),
    })


@aluno_logado
def monitor_detalhe(request, monitor_id):
    """Tela do monitor escolhido: status atual e os blocos de horário para reservar."""
    monitor = get_object_or_404(
        Monitor.objects.prefetch_related('disciplinas', 'horarios'), pk=monitor_id, expulso_em__isnull=True, aprovado=True,
    )

    agora = agora_local()
    ocupados = blocos_ocupados([monitor], agora.date())
    resumo = resumir_monitor(monitor, ocupados, agora, request.aluno.id)

    #solicitações que este aluno já fez com este monitor e ainda não terminaram
    minhas = [
        s for s in Solicitacao.objects.filter(
            aluno=request.aluno, horario__monitor=monitor, data__gte=agora.date(),
        )
        if not ja_terminou(s, agora)
    ]

    #quantos blocos o aluno ainda pode reservar em cada data (limite por dia e por monitor)
    usados = blocos_por_dia(request.aluno, monitor, agora.date())
    for vaga in resumo.vagas:
        vaga.restam = max(LIMITE_BLOCOS_POR_DIA - usados.get(vaga.data, 0), 0)

    return render(request, 'alunos/monitor.html', {
        'aluno': request.aluno,
        'monitor': monitor,
        'resumo': resumo,
        'vagas': resumo.vagas,
        'minhas': minhas,
        'limite': LIMITE_BLOCOS_POR_DIA,
        'minutos_bloco': MINUTOS_BLOCO,
        'formatos': Solicitacao.FORMATOS,
        'participantes': Solicitacao.PARTICIPANTES,
        'querystring': request.GET.urlencode(),
    })


@aluno_logado
@require_POST
def solicitar_horario(request, horario_id):
    """Reserva os blocos marcados. O agendamento é imediato: eles já ficam bloqueados para os outros."""
    #horário de monitor expulso não pode mais ser solicitado (vira 404)
    horario = get_object_or_404(
        Horario.objects.select_related('monitor'), pk=horario_id, monitor__expulso_em__isnull=True, monitor__aprovado=True,
    )
    voltar = redirect('monitor_detalhe', monitor_id=horario.monitor_id)

    assunto = request.POST.get('assunto', '').strip()
    formato = request.POST.get('formato', '')
    participantes = request.POST.get('participantes', '')
    inicios = ler_horas(request.POST.getlist('blocos'))  #um valor por bloco marcado
    try:
        data = date.fromisoformat(request.POST.get('data', ''))
    except ValueError:
        data = None

    #o navegador já exige os campos, mas o servidor confere de novo
    if not assunto:
        messages.error(request, 'Informe o assunto que você quer tratar na monitoria.')
        return voltar
    if len(assunto) > 200:
        messages.error(request, 'O assunto pode ter no máximo 200 caracteres.')
        return voltar
    if formato not in dict(Solicitacao.FORMATOS):
        messages.error(request, 'Escolha o formato do atendimento: online ou presencial.')
        return voltar
    if participantes not in dict(Solicitacao.PARTICIPANTES):
        messages.error(request, 'Informe se o atendimento será individual ou em grupo.')
        return voltar

    #as regras dos blocos (livres, do horário, limite por dia) ficam em reservas.py
    try:
        criadas = reservar(request.aluno, horario, data, inicios, assunto, formato, participantes, agora_local())
    except ReservaRecusada as motivo:
        messages.error(request, str(motivo))
        return voltar

    trechos = ', '.join(f'{s.hora_inicio:%H:%M} às {s.hora_fim:%H:%M}' for s in criadas)
    messages.success(
        request,
        f'Horário solicitado: {date_format(data, "l, d/m")}, {trechos}, com {horario.monitor.nome}.',
    )
    return voltar


@aluno_logado
def minhas_solicitacoes(request):
    """Lista as solicitações do aluno: o que ainda vai acontecer e o histórico."""
    agora = agora_local()
    todas = Solicitacao.objects.filter(aluno=request.aluno).select_related('horario__monitor')

    proximas, anteriores = [], []
    for s in todas:
        if ja_terminou(s, agora):
            anteriores.append(s)
        else:
            s.em_andamento = ja_comecou(s, agora)
            s.pode_cancelar = pode_cancelar(s, agora)
            proximas.append(s)

    anteriores.reverse()  #mais recentes primeiro

    return render(request, 'alunos/minhas.html', {
        'aluno': request.aluno,
        'proximas': proximas,
        'anteriores': anteriores[:LIMITE_HISTORICO],
    })


@aluno_logado
@require_POST
def cancelar_solicitacao(request, solicitacao_id):
    """Cancela uma solicitação do próprio aluno. Os blocos dela voltam a ficar livres."""
    #filtrar por aluno garante que ninguém cancele a solicitação de outra pessoa (vira 404)
    solicitacao = get_object_or_404(
        Solicitacao.objects.select_related('horario__monitor'),
        pk=solicitacao_id, aluno=request.aluno,
    )

    if not pode_cancelar(solicitacao, agora_local()):
        messages.error(request, 'Essa solicitação não pode mais ser cancelada, porque o atendimento já começou.')
        return redirect('minhas_solicitacoes')

    resumo = (
        f'{date_format(solicitacao.data, "l, d/m")}, '
        f'das {solicitacao.hora_inicio:%H:%M} às {solicitacao.hora_fim:%H:%M}, com {solicitacao.horario.monitor.nome}'
    )
    solicitacao.delete()
    messages.success(request, f'Solicitação cancelada: {resumo}.')
    return redirect('minhas_solicitacoes')