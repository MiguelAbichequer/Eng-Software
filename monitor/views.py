from inicio.cadastro import cadastrar

from .models import Monitor


def cadastro(request):
    #a regra do cadastro é a mesma do aluno: fica em inicio/cadastro.py
    #as disciplinas e os horários o monitor cadastra depois, no painel dele
    return cadastrar(request, Monitor, 'monitor')
