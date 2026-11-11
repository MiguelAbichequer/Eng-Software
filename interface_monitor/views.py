from collections import Counter
from datetime import time, timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.formats import date_format
from django.views.decorators.http import require_POST

from interface_aluno.disponibilidade import (
    DISPONIVEL, INDISPONIVEL,
    agora_local, datas_ocupadas, ja_comecou, ja_terminou, pode_cancelar, resumir_monitor,
)
from monitor.models import Disciplina, DiasSemana, Horario, Monitor, Solicitacao

from .decorators import monitor_logado

#quantos atendimentos passados aparecem no histórico
LIMITE_HISTORICO = 20

#por quanto tempo (em minutos) o monitor pode manter um status manual
DURACOES_STATUS = (30, 60, 120)


def _ordem(solicitacao):
    return (solicitacao.data, solicitacao.horario.hora_inicio)


def _marcados_por_horario(monitor, agora):
    """{id_do_horario: quantos atendimentos marcados ainda não terminaram}."""
    contagem = Counter()
    pendentes = Solicitacao.objects.filter(
        horario__monitor=monitor, data__gte=agora.date(),
    ).select_related('horario')
    for s in pendentes:
        if not ja_terminou(s, agora):
            contagem[s.horario_id] += 1
    return contagem


@monitor_logado
def painel(request):
    """Tela principal do monitor: como os alunos o veem agora e os atendimentos marcados."""
    monitor = request.monitor
    agora = agora_local()

    #o estado é calculado do mesmo jeito que na tela do aluno, então o monitor vê o que o aluno vê
    ocupados = datas_ocupadas([monitor], agora.date())
    resumo = resumir_monitor(monitor, ocupados, agora)

    todas = Solicitacao.objects.filter(horario__monitor=monitor).select_related('horario', 'aluno')

    proximas, anteriores = [], []
    for s in todas:
        if ja_terminou(s, agora):
            anteriores.append(s)
        else:
            s.em_andamento = ja_comecou(s, agora)
            s.pode_remover = pode_cancelar(s, agora)
            proximas.append(s)

    proximas.sort(key=_ordem)
    anteriores.sort(key=_ordem, reverse=True)  #mais recentes primeiro

    #o atendimento de agora (se o horário de agora foi solicitado) e o que vem depois dele
    atual = None
    if resumo.horario_atual:
        atual = next(
            (s for s in proximas if s.horario_id == resumo.horario_atual.id and s.data == agora.date()),
            None,
        )
    proximo = next((s for s in proximas if s is not atual), None)

    return render(request, 'interface_monitor/painel.html', {
        'monitor': monitor,
        'resumo': resumo,
        'atual': atual,
        'proximo': proximo,
        'tem_horarios': bool(monitor.horarios.all()),
        'proximas': proximas,
        'anteriores': anteriores[:LIMITE_HISTORICO],
    })


@monitor_logado
@require_POST
def alterar_status(request):
    """O monitor sobrepõe, por tempo limitado, o estado calculado pelos horários."""
    monitor = request.monitor
    escolha = request.POST.get('status', '')

    if escolha == 'automatico':
        Monitor.objects.filter(pk=monitor.pk).update(status_manual='', status_manual_ate=None)
        messages.success(request, 'Pronto: seu status voltou a seguir os seus horários.')
        return redirect('monitor_painel')

    if escolha not in (DISPONIVEL, INDISPONIVEL):
        messages.error(request, 'Escolha um status válido.')
        return redirect('monitor_painel')
    try:
        minutos = int(request.POST.get('duracao', ''))
    except ValueError:
        minutos = None
    if minutos not in DURACOES_STATUS:
        messages.error(request, 'Escolha por quanto tempo o status vale.')
        return redirect('monitor_painel')

    agora = agora_local()

    #"disponível" só muda alguma coisa fora do horário de atendimento: dentro dele o monitor
    #já aparece como disponível (ou em atendimento, se um aluno solicitou o horário)
    if escolha == DISPONIVEL:
        ocupados = datas_ocupadas([monitor], agora.date())
        if resumir_monitor(monitor, ocupados, agora).estado_automatico != INDISPONIVEL:
            messages.error(
                request,
                'Você está dentro de um horário de atendimento, então já aparece como disponível '
                'ou em atendimento. Se você tinha se marcado como indisponível, use "Voltar ao automático".',
            )
            return redirect('monitor_painel')

    ate = agora + timedelta(minutes=minutos)
    monitor.status_manual = escolha
    monitor.status_manual_ate = ate
    monitor.save(update_fields=['status_manual', 'status_manual_ate'])

    rotulo = 'disponível' if escolha == DISPONIVEL else 'indisponível'
    messages.success(
        request,
        f'Você agora aparece como {rotulo} até {ate:%H:%M}. Depois disso, o status volta a seguir os seus horários.',
    )
    return redirect('monitor_painel')


@monitor_logado
@require_POST
def remover_atendimento(request, solicitacao_id):
    """Remove uma solicitação feita com este monitor. O horário volta a ficar livre para os alunos."""
    #filtrar por monitor garante que ninguém remova o atendimento de outro monitor (vira 404)
    solicitacao = get_object_or_404(
        Solicitacao.objects.select_related('horario', 'aluno'),
        pk=solicitacao_id, horario__monitor=request.monitor,
    )

    if not pode_cancelar(solicitacao, agora_local()):
        messages.error(request, 'Esse atendimento não pode mais ser removido, porque ele já começou.')
        return redirect('monitor_painel')

    horario = solicitacao.horario
    resumo = (
        f'{date_format(solicitacao.data, "l, d/m")}, '
        f'das {horario.hora_inicio:%H:%M} às {horario.hora_fim:%H:%M}, com {solicitacao.aluno.nome}'
    )
    solicitacao.delete()
    messages.success(request, f'Atendimento removido: {resumo}. O horário voltou a ficar livre.')
    return redirect('monitor_painel')


@monitor_logado
def horarios(request):
    """Os horários semanais de atendimento do monitor, para cadastrar e remover."""
    monitor = request.monitor
    marcados = _marcados_por_horario(monitor, agora_local())
    todos = list(monitor.horarios.all())

    dias = []
    for valor, rotulo in DiasSemana.choices:
        do_dia = [h for h in todos if h.dia_semana == valor]
        for h in do_dia:
            h.marcados = marcados[h.id]
        if do_dia:
            dias.append((rotulo, do_dia))

    return render(request, 'interface_monitor/horarios.html', {
        'monitor': monitor,
        'dias': dias,
        'dias_semana': DiasSemana.choices,
        'total': len(todos),
    })


def _hora(texto):
    try:
        return time.fromisoformat(texto)
    except ValueError:
        return None


@monitor_logado
@require_POST
def novo_horario(request):
    """Cadastra um horário semanal. As regras (fim depois do início, sem sobreposição) ficam no model."""
    try:
        dia = int(request.POST.get('dia_semana', ''))
    except ValueError:
        dia = None
    inicio = _hora(request.POST.get('hora_inicio', ''))
    fim = _hora(request.POST.get('hora_fim', ''))

    #o navegador já exige os campos, mas o servidor confere de novo
    if dia not in DiasSemana.values:
        messages.error(request, 'Escolha o dia da semana.')
        return redirect('monitor_horarios')
    if inicio is None or fim is None:
        messages.error(request, 'Informe a hora de início e a hora de fim.')
        return redirect('monitor_horarios')

    horario = Horario(monitor=request.monitor, dia_semana=dia, hora_inicio=inicio, hora_fim=fim)
    try:
        horario.full_clean()
    except ValidationError as erro:
        messages.error(request, ' '.join(erro.messages))
        return redirect('monitor_horarios')

    horario.save()
    messages.success(
        request,
        f'Horário cadastrado: {horario.get_dia_semana_display()}, '
        f'das {inicio:%H:%M} às {fim:%H:%M}. Ele já aparece para os alunos.',
    )
    return redirect('monitor_horarios')


@monitor_logado
@require_POST
def remover_horario(request, horario_id):
    """Remove um horário semanal, desde que nenhum aluno tenha um atendimento marcado nele."""
    #filtrar por monitor garante que ninguém remova o horário de outro monitor (vira 404)
    horario = get_object_or_404(Horario, pk=horario_id, monitor=request.monitor)

    #apagar o horário apagaria junto as solicitações dele, e o aluno perderia o atendimento sem aviso
    marcados = _marcados_por_horario(request.monitor, agora_local())[horario.id]
    if marcados:
        messages.error(
            request,
            f'Esse horário tem {marcados} atendimento{"s" if marcados > 1 else ""} marcado{"s" if marcados > 1 else ""}. '
            'Remova-o em "Atendimentos" antes de apagar o horário.',
        )
        return redirect('monitor_horarios')

    descricao = f'{horario.get_dia_semana_display()}, das {horario.hora_inicio:%H:%M} às {horario.hora_fim:%H:%M}'
    horario.delete()
    messages.success(request, f'Horário removido: {descricao}.')
    return redirect('monitor_horarios')


@monitor_logado
def disciplinas(request):
    """As disciplinas em que o monitor atende: escolher entre as que existem ou cadastrar uma nova."""
    return render(request, 'interface_monitor/disciplinas.html', {
        'monitor': request.monitor,
        'todas': Disciplina.objects.order_by('nome'),
        'marcadas': set(request.monitor.disciplinas.values_list('id', flat=True)),
    })


@monitor_logado
@require_POST
def salvar_disciplinas(request):
    """Grava a lista marcada. Desmarcar só tira a disciplina do monitor, ela continua existindo."""
    ids = [int(valor) for valor in request.POST.getlist('disciplinas') if valor.isdigit()]
    #filtrar pelo banco ignora ids que não existem
    escolhidas = Disciplina.objects.filter(pk__in=ids)
    request.monitor.disciplinas.set(escolhidas)

    total = escolhidas.count()
    if total:
        messages.success(request, f'Disciplinas salvas: você atende em {total}.')
    else:
        messages.success(request, 'Disciplinas salvas. Você não está associado a nenhuma disciplina.')
    return redirect('monitor_disciplinas')


@monitor_logado
@require_POST
def nova_disciplina(request):
    """Cadastra uma disciplina que ainda não existe e já a associa ao monitor."""
    codigo = request.POST.get('codigo', '').strip().upper()
    nome = ' '.join(request.POST.get('nome', '').split())  #tira espaços sobrando

    if not codigo or not nome:
        messages.error(request, 'Informe o código e o nome da disciplina.')
        return redirect('monitor_disciplinas')
    if len(codigo) > 20:
        messages.error(request, 'O código pode ter no máximo 20 caracteres.')
        return redirect('monitor_disciplinas')
    if len(nome) > 100:
        messages.error(request, 'O nome pode ter no máximo 100 caracteres.')
        return redirect('monitor_disciplinas')

    #o código é único: se já existe (mesmo escrito com outras maiúsculas), usa a que está lá
    #em vez de criar outra ou trocar o nome que outros monitores já enxergam
    existente = Disciplina.objects.filter(codigo__iexact=codigo).first()
    if existente is None:
        try:
            with transaction.atomic():
                existente = Disciplina.objects.create(codigo=codigo, nome=nome)
            criada = True
        except IntegrityError:
            #outra pessoa cadastrou o mesmo código um instante antes
            existente = Disciplina.objects.get(codigo__iexact=codigo)
            criada = False
    else:
        criada = False

    request.monitor.disciplinas.add(existente)
    if criada:
        messages.success(request, f'Disciplina cadastrada e adicionada às suas: {existente.nome}.')
    else:
        messages.success(
            request,
            f'Já existia uma disciplina com o código {existente.codigo} ("{existente.nome}"). '
            'Ela foi adicionada às suas disciplinas.',
        )
    return redirect('monitor_disciplinas')
