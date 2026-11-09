import csv

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from monitor.models import Monitor

from . import relatorio


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
    """Relatório de atendimentos: resumo, por dia, horários, assuntos e monitores."""
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
