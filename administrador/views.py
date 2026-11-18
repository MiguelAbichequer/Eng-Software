import csv

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from alunos.models import Aluno
from interface_aluno.disponibilidade import agora_local
from monitor.models import Monitor

from . import relatorio, usuarios
from .models import Denuncia


def _filtros(request):
    """Lê período e monitor da URL (?inicio=...&fim=...&monitor=...)."""
    hoje = timezone.localdate()
    periodo, erro = relatorio.ler_periodo(
        request.GET.get('inicio', '').strip(),
        request.GET.get('fim', '').strip(),
        hoje,
    )
    monitor_txt = request.GET.get('monitor', '')
    monitor = Monitor.objects.filter(pk=monitor_txt).first() if monitor_txt.isdigit() else None
    return periodo, monitor, erro


#staff_member_required: só entra quem fez login no /admin/ com um usuário "membro da equipe"
#(o superusuário criado com createsuperuser já é). Quem não está logado vai para o login do admin.
@staff_member_required
def relatorio_view(request):
    """Relatório de atendimentos: resumo, por dia, horários e monitores."""
    periodo, monitor, erro = _filtros(request)
    dados = relatorio.montar(periodo, monitor.id if monitor else None)

    return render(request, 'administrador/relatorio.html', {
        **dados,
        'periodo': periodo,
        'monitor_escolhido': monitor,
        'lista_monitores': Monitor.objects.order_by('nome'),
        'erro': erro,
        'querystring': request.GET.urlencode(),
    })


@staff_member_required
def relatorio_csv(request):
    """Exporta as solicitações do período, uma por linha, para abrir no Excel ou Planilhas."""
    periodo, monitor, _ = _filtros(request)
    solicitacoes = (
        relatorio.solicitacoes_do_periodo(periodo, monitor.id if monitor else None)
        .select_related('aluno', 'horario__monitor')
        .order_by('data', 'hora_inicio')
    )

    nome = f'relatorio_{periodo.inicio:%Y-%m-%d}_a_{periodo.fim:%Y-%m-%d}.csv'
    resposta = HttpResponse(content_type='text/csv; charset=utf-8')
    resposta['Content-Disposition'] = f'attachment; filename="{nome}"'

    #o BOM (﻿) faz o Excel reconhecer os acentos; ";" é o separador do Excel em português
    resposta.write('﻿')
    escritor = csv.writer(resposta, delimiter=';')
    escritor.writerow([
        'Data', 'Início', 'Fim', 'Monitor', 'Aluno', 'Matrícula',
        'Assunto', 'Formato', 'Participantes', 'Solicitada em',
    ])
    for s in solicitacoes:
        escritor.writerow([
            f'{s.data:%d/%m/%Y}',
            f'{s.hora_inicio:%H:%M}',
            f'{s.hora_fim:%H:%M}',
            s.horario.monitor.nome,
            s.aluno.nome,
            s.aluno.matricula,
            s.assunto,
            s.get_formato_display(),
            s.get_participantes_display(),
            f'{timezone.localtime(s.criada_em):%d/%m/%Y %H:%M}',
        ])
    return resposta


# ---------------------------------------------------------------------------
# Consultar e expulsar usuários
# ---------------------------------------------------------------------------

@staff_member_required
def usuarios_view(request):
    """Lista de alunos e monitores, com busca por nome ou matrícula."""
    busca = request.GET.get('busca', '').strip()
    tipo = request.GET.get('tipo', '')
    situacao = request.GET.get('situacao', '')
    if tipo not in usuarios.TIPOS:
        tipo = ''
    if situacao not in ('ativos', 'expulsos'):
        situacao = ''

    linhas = usuarios.listar(busca, tipo, situacao)
    return render(request, 'administrador/usuarios.html', {
        'linhas': linhas,
        'filtros': {'busca': busca, 'tipo': tipo, 'situacao': situacao},
        'filtrando': bool(busca or tipo or situacao),
        'total_expulsos': sum(1 for l in linhas if l.usuario.expulso),
    })


@staff_member_required
def usuario_view(request, tipo, usuario_id):
    """Ficha de um aluno ou monitor: dados, atendimentos e a opção de expulsar ou readmitir."""
    modelo = usuarios.modelo_do_tipo(tipo)
    usuario = get_object_or_404(modelo, pk=usuario_id)
    agora = agora_local()

    proximas, anteriores = usuarios.separar(usuarios.solicitacoes_de(usuario), agora)

    contexto = {
        'tipo': tipo,
        'usuario': usuario,
        'proximas': proximas,
        'anteriores': anteriores[:usuarios.LIMITE_HISTORICO],
        'total': len(proximas) + len(anteriores),
        'realizadas': len(anteriores),
        #o aviso no formulário de expulsão diz quantos atendimentos seriam cancelados
        'a_cancelar': 0 if usuario.expulso else len(usuarios.canceladas_ao_expulsar(usuario, agora)),
        'limite_historico': usuarios.LIMITE_HISTORICO,
    }
    if tipo == 'aluno':
        contexto['denuncias'] = list(usuario.denuncias.select_related('monitor'))
    if tipo == 'monitor':
        contexto['horarios'] = list(usuario.horarios.all())
        contexto['disciplinas'] = list(usuario.disciplinas.order_by('nome'))
    return render(request, 'administrador/usuario.html', contexto)


@staff_member_required
@require_POST
def expulsar_view(request, tipo, usuario_id):
    """Bloqueia o acesso do usuário e cancela os atendimentos dele que ainda não começaram."""
    modelo = usuarios.modelo_do_tipo(tipo)
    usuario = get_object_or_404(modelo, pk=usuario_id)
    voltar = redirect('usuario', tipo=tipo, usuario_id=usuario.id)

    if usuario.expulso:
        messages.error(request, f'{usuario.nome} já está expulso.')
        return voltar

    motivo = ' '.join(request.POST.get('motivo', '').split())
    if not motivo:
        messages.error(request, 'Informe o motivo da expulsão.')
        return voltar
    if len(motivo) > 200:
        messages.error(request, 'O motivo pode ter no máximo 200 caracteres.')
        return voltar
    if request.POST.get('confirmo') != 'sim':
        messages.error(request, 'Marque a caixa de confirmação para expulsar.')
        return voltar

    canceladas = usuarios.expulsar(usuario, motivo, agora_local())
    texto = f'{usuario.nome} foi expulso e não consegue mais entrar no sistema.'
    if canceladas:
        texto += f' {canceladas} atendimento{"s" if canceladas > 1 else ""} futuro{"s" if canceladas > 1 else ""} cancelado{"s" if canceladas > 1 else ""}.'
    messages.success(request, texto)
    return voltar


@staff_member_required
@require_POST
def readmitir_view(request, tipo, usuario_id):
    """Desfaz a expulsão."""
    modelo = usuarios.modelo_do_tipo(tipo)
    usuario = get_object_or_404(modelo, pk=usuario_id)

    if usuario.expulso:
        usuarios.readmitir(usuario)
        messages.success(request, f'{usuario.nome} foi readmitido e já pode entrar no sistema.')
    return redirect('usuario', tipo=tipo, usuario_id=usuario.id)


# ---------------------------------------------------------------------------
# Aprovação de monitores
# ---------------------------------------------------------------------------

def _monitor_pendente(monitor_id):
    #só monitores ainda não aprovados (e não expulsos) entram nesta fila
    return get_object_or_404(Monitor, pk=monitor_id, aprovado=False, expulso_em__isnull=True)


@staff_member_required
def monitores_pendentes_view(request):
    """Fila de cadastros de monitor esperando aprovação, dos mais antigos para os mais novos."""
    pendentes = (
        Monitor.objects.filter(aprovado=False, expulso_em__isnull=True)
        .prefetch_related('disciplinas')
        .order_by('cadastrado_em', 'nome')
    )
    return render(request, 'administrador/monitores_pendentes.html', {'pendentes': pendentes})


@staff_member_required
@require_POST
def aprovar_monitor_view(request, monitor_id):
    """Aprova o cadastro: o monitor passa a conseguir entrar e a aparecer para os alunos."""
    monitor = _monitor_pendente(monitor_id)
    monitor.aprovado = True
    monitor.save(update_fields=['aprovado'])
    messages.success(request, f'{monitor.nome} foi aprovado como monitor e já pode entrar no sistema.')
    return redirect('monitores_pendentes')


@staff_member_required
@require_POST
def recusar_monitor_view(request, monitor_id):
    """
    Recusa o cadastro apagando a conta. Como o monitor nunca foi aprovado, ele não tem
    horários com reservas nem histórico; e a matrícula fica livre para um novo cadastro.
    """
    monitor = _monitor_pendente(monitor_id)
    nome = monitor.nome
    monitor.delete()
    messages.success(request, f'O cadastro de {nome} foi recusado e apagado.')
    return redirect('monitores_pendentes')


# ---------------------------------------------------------------------------
# Aprovação de alunos (cadastro com documento de confirmação)
# ---------------------------------------------------------------------------

def _aluno_pendente(aluno_id):
    #só alunos ainda não aprovados (e não expulsos) entram nesta fila
    return get_object_or_404(Aluno, pk=aluno_id, aprovado=False, expulso_em__isnull=True)


@staff_member_required
def alunos_pendentes_view(request):
    """Fila de cadastros de aluno esperando a conferência do documento, dos mais antigos para os mais novos."""
    pendentes = (
        Aluno.objects.filter(aprovado=False, expulso_em__isnull=True)
        .order_by('cadastrado_em', 'nome')
    )
    return render(request, 'administrador/alunos_pendentes.html', {'pendentes': pendentes})


@staff_member_required
def documento_aluno_view(request, aluno_id):
    """
    Abre o documento de confirmação enviado pelo aluno, dentro do próprio sistema.
    O arquivo não tem URL pública: só quem está logado como administrador chega até aqui.
    """
    aluno = get_object_or_404(Aluno, pk=aluno_id)
    if not aluno.documento_confirmacao:
        raise Http404('Este cadastro não tem documento.')
    try:
        arquivo = aluno.documento_confirmacao.open('rb')
    except FileNotFoundError:
        raise Http404('O arquivo do documento não foi encontrado.')
    #inline: abre no navegador em vez de baixar; o nome do arquivo vem do cadastro
    return FileResponse(arquivo, as_attachment=False, filename=aluno.documento_confirmacao.name.rsplit('/', 1)[-1])


@staff_member_required
@require_POST
def aprovar_aluno_view(request, aluno_id):
    """Aprova o cadastro depois de conferir o documento: o aluno passa a conseguir entrar."""
    aluno = _aluno_pendente(aluno_id)
    aluno.aprovado = True
    aluno.save(update_fields=['aprovado'])
    messages.success(request, f'{aluno.nome} foi aprovado e já pode entrar no sistema.')
    return redirect('alunos_pendentes')


@staff_member_required
@require_POST
def recusar_aluno_view(request, aluno_id):
    """
    Recusa o cadastro: apaga a conta e o documento enviado. Como o aluno nunca foi aprovado,
    ele não tem solicitações nem histórico; e a matrícula fica livre para um novo cadastro.
    """
    aluno = _aluno_pendente(aluno_id)
    nome = aluno.nome
    if aluno.documento_confirmacao:
        aluno.documento_confirmacao.delete(save=False)
    aluno.delete()
    messages.success(request, f'O cadastro de {nome} foi recusado e apagado.')
    return redirect('alunos_pendentes')


# ---------------------------------------------------------------------------
# Denúncias de alunos feitas pelos monitores
# ---------------------------------------------------------------------------

#quantas denúncias já resolvidas aparecem embaixo das pendentes
LIMITE_DENUNCIAS_RESOLVIDAS = 20


@staff_member_required
def denuncias_view(request):
    """As denúncias pendentes (mais antigas primeiro) e as últimas já resolvidas."""
    todas = Denuncia.objects.select_related('aluno', 'monitor')
    return render(request, 'administrador/denuncias.html', {
        'pendentes': todas.filter(situacao=Denuncia.PENDENTE).order_by('criada_em'),
        'resolvidas': todas.exclude(situacao=Denuncia.PENDENTE).order_by('-resolvida_em')[:LIMITE_DENUNCIAS_RESOLVIDAS],
    })


def _denuncia_pendente(denuncia_id):
    return get_object_or_404(Denuncia.objects.select_related('aluno', 'monitor'), pk=denuncia_id, situacao=Denuncia.PENDENTE)


@staff_member_required
@require_POST
def expulsar_por_denuncia_view(request, denuncia_id):
    """
    Expulsa o aluno denunciado, com a mesma expulsão da ficha do usuário (reversível,
    cancela os atendimentos futuros). As outras denúncias pendentes dele são resolvidas junto.
    """
    denuncia = _denuncia_pendente(denuncia_id)
    aluno = denuncia.aluno
    agora = agora_local()

    if not aluno.expulso:
        quem = denuncia.monitor.nome if denuncia.monitor else 'monitor'
        #o motivo da expulsão tem até 200 caracteres; a denúncia completa continua guardada
        motivo = f'Denúncia de {quem}: {denuncia.motivo}'
        if len(motivo) > 200:
            motivo = motivo[:197] + '...'
        canceladas = usuarios.expulsar(aluno, motivo, agora)
        texto = f'{aluno.nome} foi expulso.'
        if canceladas:
            texto += f' {canceladas} atendimento{"s" if canceladas > 1 else ""} futuro{"s" if canceladas > 1 else ""} cancelado{"s" if canceladas > 1 else ""}.'
    else:
        texto = f'{aluno.nome} já estava expulso; a denúncia foi encerrada.'

    Denuncia.objects.filter(aluno=aluno, situacao=Denuncia.PENDENTE).update(situacao=Denuncia.EXPULSO, resolvida_em=agora)
    messages.success(request, texto)
    return redirect('denuncias')


@staff_member_required
@require_POST
def arquivar_denuncia_view(request, denuncia_id):
    """Encerra a denúncia sem punir o aluno."""
    denuncia = _denuncia_pendente(denuncia_id)
    denuncia.situacao = Denuncia.ARQUIVADA
    denuncia.resolvida_em = agora_local()
    denuncia.save(update_fields=['situacao', 'resolvida_em'])
    messages.success(request, f'Denúncia sobre {denuncia.aluno.nome} arquivada, sem punição.')
    return redirect('denuncias')
