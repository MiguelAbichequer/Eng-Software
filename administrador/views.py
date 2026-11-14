import csv

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from interface_aluno.disponibilidade import agora_local
from monitor.models import Monitor

from . import relatorio, usuarios


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
        .order_by('data', 'horario__hora_inicio')
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
            f'{s.horario.hora_inicio:%H:%M}',
            f'{s.horario.hora_fim:%H:%M}',
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
