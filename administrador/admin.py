from django.contrib import admin

#troca a página inicial do /admin/ por uma versão com o link para o relatório
admin.site.index_template = 'administrador/admin_index.html'

from .models import Denuncia


@admin.register(Denuncia)
class DenunciaAdmin(admin.ModelAdmin):
    #as decisões (expulsar ou arquivar) são tomadas na tela /administrador/denuncias/
    list_display = ['criada_em', 'aluno', 'monitor', 'situacao']
    list_filter = ['situacao']
    search_fields = ['aluno__nome', 'monitor__nome', 'motivo']
