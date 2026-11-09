from django.urls import path
from . import views

urlpatterns = [
    path('relatorio/', views.relatorio_view, name='relatorio'),
    path('relatorio/csv/', views.relatorio_csv, name='relatorio_csv'),
]
