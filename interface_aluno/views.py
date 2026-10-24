from datetime import date

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.formats import date_format
from django.views.decorators.http import require_POST

from monitor.models import Disciplina, Horario, Monitor, Solicitacao

from .decorators import aluno_logado
from .disponibilidade import (
    DISPONIVEL, EM_ATENDIMENTO, INDISPONIVEL,
    agora_local, datas_da_janela, datas_ocupadas, ja_comecou, ja_terminou,
    pode_cancelar, resumir_monitor,
)

#na lista, quem está disponível agora aparece primeiro
ORDEM_ESTADO = {DISPONIVEL: 0, EM_ATENDIMENTO: 1, INDISPONIVEL: 2}

#quantos atendimentos passados aparecem no histórico
LIMITE_HISTORICO = 20


@aluno_logado
def painel(request):
    """Tela principal do aluno: lista de monitores com filtros."""
    nome = request.GET.get('nome', '').strip()
    disciplina_id = request.GET.get('disciplina', '')
    disponibilidade = request.GET.get('disponibilidade', '')

    monitores = Monitor.objects.prefetch_related('disciplinas', 'horarios')
    if nome:
        monitores = monitores.filter(nome__icontains=nome)
    if disciplina_id.isdigit():
        monitores = monitores.filter(disciplinas__id=int(disciplina_id))
    monitores = list(monitores.order_by('nome'))

    agora = agora_local()
    ocupados = datas_ocupadas(monitores, agora.date())
    resumos = [resumir_monitor(m, ocupados, agora) for m in monitores]

    #a disponibilidade é calculada (não fica no banco), então este filtro é aplicado aqui
    if disponibilidade == 'agora':
        resumos = [r for r in resumos if r.estado == DISPONIVEL]
    elif disponibilidade == 'livres':
        resumos = [r for r in resumos if r.vagas]

    resumos.sort(key=lambda r: ORDEM_ESTADO[r.estado])  #sort é estável: mantém a ordem por nome

    return render(request, 'interface_aluno/painel.html', {
        'aluno': request.aluno,
        'resumos': resumos,
        #só oferece no filtro as disciplinas que têm pelo menos um monitor
        'disciplinas': Disciplina.objects.filter(monitores__isnull=False).distinct(),
        'filtros': {'nome': nome, 'disciplina': disciplina_id, 'disponibilidade': disponibilidade},
        'filtrando': bool(nome or disciplina_id or disponibilidade),
        'querystring': request.GET.urlencode(),
    })


@aluno_logado
def monitor_detalhe(request, monitor_id):
    """Tela do monitor escolhido: disponibilidade atual e horários para solicitar."""
    monitor = get_object_or_404(Monitor.objects.prefetch_related('disciplinas', 'horarios'), pk=monitor_id)

    agora = agora_local()
    ocupados = datas_ocupadas([monitor], agora.date())
    resumo = resumir_monitor(monitor, ocupados, agora)

    #se o horário de agora está ocupado, descobre se foi o próprio aluno que solicitou
    atual_e_meu = bool(
        resumo.horario_atual
        and ocupados.get((resumo.horario_atual.id, agora.date())) == request.aluno.id
    )

    #solicitações que este aluno já fez com este monitor e ainda não aconteceram
    minhas = [
        s for s in Solicitacao.objects.filter(
            aluno=request.aluno, horario__monitor=monitor, data__gte=agora.date(),
        ).select_related('horario')
        if s.data > agora.date() or s.horario.hora_fim > agora.time()
    ]

    return render(request, 'interface_aluno/monitor.html', {
        'aluno': request.aluno,
        'monitor': monitor,
        'resumo': resumo,
        'atual_e_meu': atual_e_meu,
        'vagas': resumo.vagas,
        'minhas': minhas,
        'formatos': Solicitacao.FORMATOS,
        'participantes': Solicitacao.PARTICIPANTES,
        'querystring': request.GET.urlencode(),
    })


@aluno_logado
@require_POST
def solicitar_horario(request, horario_id):
    """Cria a solicitação. O agendamento é imediato: o horário já fica reservado."""
    horario = get_object_or_404(Horario.objects.select_related('monitor'), pk=horario_id)
    voltar = redirect('monitor_detalhe', monitor_id=horario.monitor_id)

    assunto = request.POST.get('assunto', '').strip()
    formato = request.POST.get('formato', '')
    participantes = request.POST.get('participantes', '')
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
    if data not in datas_da_janela(horario, agora_local()):
        messages.error(request, 'Essa data não está mais disponível para solicitação.')
        return voltar

    try:
        with transaction.atomic():
            Solicitacao.objects.create(
                aluno=request.aluno, horario=horario, data=data,
                assunto=assunto, formato=formato, participantes=participantes,
            )
    except IntegrityError:
        #outro aluno reservou o mesmo horário um instante antes
        messages.error(request, 'Esse horário acabou de ser solicitado por outra pessoa. Escolha outro.')
        return voltar

    messages.success(
        request,
        f'Horário solicitado: {date_format(data, "l, d/m")}, '
        f'das {horario.hora_inicio:%H:%M} às {horario.hora_fim:%H:%M}, com {horario.monitor.nome}.',
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

    return render(request, 'interface_aluno/minhas.html', {
        'aluno': request.aluno,
        'proximas': proximas,
        'anteriores': anteriores[:LIMITE_HISTORICO],
    })


@aluno_logado
@require_POST
def cancelar_solicitacao(request, solicitacao_id):
    """Cancela uma solicitação do próprio aluno. O horário volta a ficar livre para os outros."""
    #filtrar por aluno garante que ninguém cancele a solicitação de outra pessoa (vira 404)
    solicitacao = get_object_or_404(
        Solicitacao.objects.select_related('horario__monitor'),
        pk=solicitacao_id, aluno=request.aluno,
    )

    if not pode_cancelar(solicitacao, agora_local()):
        messages.error(request, 'Essa solicitação não pode mais ser cancelada, porque o atendimento já começou.')
        return redirect('minhas_solicitacoes')

    horario = solicitacao.horario
    resumo = (
        f'{date_format(solicitacao.data, "l, d/m")}, '
        f'das {horario.hora_inicio:%H:%M} às {horario.hora_fim:%H:%M}, com {horario.monitor.nome}'
    )
    solicitacao.delete()
    messages.success(request, f'Solicitação cancelada: {resumo}.')
    return redirect('minhas_solicitacoes')