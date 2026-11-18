from django.urls import path
from . import views

urlpatterns = [
    path('relatorio/', views.relatorio_view, name='relatorio'),
    path('relatorio/csv/', views.relatorio_csv, name='relatorio_csv'),
    path('usuarios/', views.usuarios_view, name='usuarios'),
    path('solicitacoes-de-monitor/', views.monitores_pendentes_view, name='monitores_pendentes'),
    path('solicitacoes-de-monitor/<int:monitor_id>/aprovar/', views.aprovar_monitor_view, name='monitor_aprovar'),
    path('solicitacoes-de-monitor/<int:monitor_id>/recusar/', views.recusar_monitor_view, name='monitor_recusar'),
    #<tipo> é 'aluno' ou 'monitor': são duas tabelas diferentes, então o id sozinho não basta
    path('usuarios/<str:tipo>/<int:usuario_id>/', views.usuario_view, name='usuario'),
    path('usuarios/<str:tipo>/<int:usuario_id>/expulsar/', views.expulsar_view, name='usuario_expulsar'),
    path('usuarios/<str:tipo>/<int:usuario_id>/readmitir/', views.readmitir_view, name='usuario_readmitir'),
]
