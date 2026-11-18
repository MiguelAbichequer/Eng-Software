"""
Contadores que aparecem no menu das telas do administrador ("Solicitações 2", "Denúncias 1").

Um "context processor" é uma função que o Django chama em toda página renderizada;
o dicionário que ela devolve fica disponível em todos os templates. Está registrado em
config/settings.py (TEMPLATES > OPTIONS > context_processors).
"""

from monitor.models import Monitor

from .models import Denuncia


def pendencias(request):
    #só interessa ao administrador logado; para os outros não faz consulta nenhuma
    usuario = getattr(request, 'user', None)
    if not (usuario and usuario.is_authenticated and usuario.is_staff):
        return {}
    return {
        'monitores_pendentes_total': Monitor.objects.filter(aprovado=False, expulso_em__isnull=True).count(),
        'denuncias_pendentes_total': Denuncia.objects.filter(situacao=Denuncia.PENDENTE).count(),
    }
