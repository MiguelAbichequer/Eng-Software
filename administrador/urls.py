from django.urls import path
from . import views

urlpatterns = [
    path('relatorio/', views.relatorio_view, name='relatorio'),
    path('relatorio/csv/', views.relatorio_csv, name='relatorio_csv'),
    path('usuarios/', views.usuarios_view, name='usuarios'),
    path('solicitacoes-de-monitor/', views.monitores_pendentes_view, name='monitores_pendentes'),
    path('denuncias/', views.denuncias_view, name='denuncias'),
    path('denuncias/<int:denuncia_id>/expulsar/', views.expulsar_por_denuncia_view, name='denuncia_expulsar'),
    path('denuncias/<int:denuncia_id>/arquivar/', views.arquivar_denuncia_view, name='denuncia_arquivar'),
    path('solicitacoes-de-aluno/', views.alunos_pendentes_view, name='alunos_pendentes'),
    path('solicitacoes-de-aluno/<int:aluno_id>/documento/', views.documento_aluno_view, name='aluno_documento'),
    path('solicitacoes-de-aluno/<int:aluno_id>/aprovar/', views.aprovar_aluno_view, name='aluno_aprovar'),
    path('solicitacoes-de-aluno/<int:aluno_id>/recusar/', views.recusar_aluno_view, name='aluno_recusar'),
    path('solicitacoes-de-monitor/<int:monitor_id>/aprovar/', views.aprovar_monitor_view, name='monitor_aprovar'),
    path('solicitacoes-de-monitor/<int:monitor_id>/recusar/', views.recusar_monitor_view, name='monitor_recusar'),
    #<tipo> é 'aluno' ou 'monitor': são duas tabelas diferentes, então o id sozinho não basta
    path('usuarios/<str:tipo>/<int:usuario_id>/', views.usuario_view, name='usuario'),
    path('usuarios/<str:tipo>/<int:usuario_id>/expulsar/', views.expulsar_view, name='usuario_expulsar'),
    path('usuarios/<str:tipo>/<int:usuario_id>/readmitir/', views.readmitir_view, name='usuario_readmitir'),
]
