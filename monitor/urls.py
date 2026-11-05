from django.urls import path
from . import views

urlpatterns = [
    path('', views.painel, name='monitor_painel'),
    path('atendimentos/<int:solicitacao_id>/remover/', views.remover_atendimento, name='monitor_atendimento_remover'),
    path('horarios/', views.horarios, name='monitor_horarios'),
    path('horarios/novo/', views.novo_horario, name='monitor_horario_novo'),
    path('horarios/<int:horario_id>/remover/', views.remover_horario, name='monitor_horario_remover'),
]