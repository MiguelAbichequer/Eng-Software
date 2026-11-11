from inicio.cadastro import cadastrar

from .models import Aluno


def cadastro(request):
    #a regra do cadastro é a mesma do monitor: fica em inicio/cadastro.py
    return cadastrar(request, Aluno, 'aluno')
