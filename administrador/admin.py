from django.contrib import admin

#troca a página inicial do /admin/ por uma versão com o link para o relatório
admin.site.index_template = 'administrador/admin_index.html'
