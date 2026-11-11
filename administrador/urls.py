from django.urls import path
from . import views

urlpatterns = [
    path('relatorio/', views.relatorio_view, name='relatorio'),
    path('relatorio/csv/', views.relatorio_csv, name='relatorio_csv'),
    path('usuarios/', views.usuarios_view, name='usuarios'),
    #<tipo> é 'aluno' ou 'monitor': são duas tabelas diferentes, então o id sozinho não basta
    path('usuarios/<str:tipo>/<int:usuario_id>/', views.usuario_view, name='usuario'),
    path('usuarios/<str:tipo>/<int:usuario_id>/expulsar/', views.expulsar_view, name='usuario_expulsar'),
    path('usuarios/<str:tipo>/<int:usuario_id>/readmitir/', views.readmitir_view, name='usuario_readmitir'),
]
