from inicio.cadastro import cadastrar

from .models import Monitor


def cadastro(request):
    #a regra do cadastro é a mesma do aluno: fica em inicio/cadastro.py
    #as disciplinas e os horários o monitor cadastra depois, no painel dele
    #o cadastro de monitor precisa ser aprovado por um administrador antes de valer
    #o monitor também envia um documento de confirmação, como o aluno
    return cadastrar(request, Monitor, 'monitor', precisa_aprovacao=True, exige_documento=True)
