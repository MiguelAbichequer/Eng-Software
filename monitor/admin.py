from django.contrib import admin

from .models import Disciplina, Horario, Monitor, Solicitacao


class HorarioInline(admin.TabularInline):
    model = Horario
    extra = 1


@admin.register(Disciplina)
class DisciplinaAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'nome']
    search_fields = ['codigo', 'nome']


@admin.register(Monitor)
class MonitorAdmin(admin.ModelAdmin):
    list_display = ['nome', 'matricula']
    search_fields = ['nome', 'matricula']
    filter_horizontal = ['disciplinas']
    inlines = [HorarioInline]


@admin.register(Solicitacao)
class SolicitacaoAdmin(admin.ModelAdmin):
    list_display = ['data', 'horario', 'aluno', 'assunto', 'formato', 'participantes']
    list_filter = ['formato', 'participantes', 'data']
    search_fields = ['aluno__nome', 'horario__monitor__nome', 'assunto']