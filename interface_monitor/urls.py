from django.urls import path
from . import views

urlpatterns = [
    path('', views.painel, name='monitor_painel'),
    path('status/', views.alterar_status, name='monitor_status'),
    path('atendimentos/<int:solicitacao_id>/remover/', views.remover_atendimento, name='monitor_atendimento_remover'),
    path('alunos/<int:aluno_id>/denunciar/', views.denunciar_aluno, name='monitor_denunciar'),
    path('disciplinas/', views.disciplinas, name='monitor_disciplinas'),
    path('disciplinas/salvar/', views.salvar_disciplinas, name='monitor_disciplinas_salvar'),
    path('disciplinas/nova/', views.nova_disciplina, name='monitor_disciplina_nova'),
    path('horarios/', views.horarios, name='monitor_horarios'),
    path('horarios/novo/', views.novo_horario, name='monitor_horario_novo'),
    path('horarios/<int:horario_id>/remover/', views.remover_horario, name='monitor_horario_remover'),
]
