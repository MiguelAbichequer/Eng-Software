from django.contrib import admin
from django.contrib.auth.hashers import make_password

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
    list_display = ['nome', 'matricula', 'aprovado']
    list_filter = ['aprovado']
    search_fields = ['nome', 'matricula']
    filter_horizontal = ['disciplinas']
    inlines = [HorarioInline]

    #a senha digitada no admin é guardada com hash, como no cadastro
    #(para monitores já existentes: digite uma senha nova no campo e salve)
    def save_model(self, request, obj, form, change):
        if 'senha' in form.changed_data and obj.senha:
            obj.senha = make_password(obj.senha)
        super().save_model(request, obj, form, change)


@admin.register(Solicitacao)
class SolicitacaoAdmin(admin.ModelAdmin):
    list_display = ['data', 'horario', 'aluno', 'assunto', 'formato', 'participantes']
    list_filter = ['formato', 'participantes', 'data']
    search_fields = ['aluno__nome', 'horario__monitor__nome', 'assunto']