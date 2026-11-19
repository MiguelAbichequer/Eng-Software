from django.urls import path
from . import views

urlpatterns = [
    path('cadastro/', views.cadastro, name='cadastro_aluno'),
    path('painel/', views.painel, name='painel'),
    path('monitor/<int:monitor_id>/', views.monitor_detalhe, name='monitor_detalhe'),
    path('solicitar/<int:horario_id>/', views.solicitar_horario, name='solicitar_horario'),
    path('minhas/', views.minhas_solicitacoes, name='minhas_solicitacoes'),
    path('minhas/<int:solicitacao_id>/cancelar/', views.cancelar_solicitacao, name='cancelar_solicitacao'),
]
