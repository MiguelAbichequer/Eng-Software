from inicio.cadastro import cadastrar

from .models import Aluno


def cadastro(request):
    #a regra do cadastro é a mesma do monitor: fica em inicio/cadastro.py
    #o aluno envia um documento de confirmação e só entra depois que o administrador aprovar
    return cadastrar(request, Aluno, 'aluno', precisa_aprovacao=True, exige_documento=True)
