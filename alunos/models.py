# """exemplo""" - string usada para documentar classes
#app alunos que o django fará a comunicação do python com o mysql

#arquivo models é utilizado para definir as classes que serão transformadas em tabelas pelo django
#Model é o comando que diz ao django que deve tratar o dado como um modelo de dados

from django.db import models

#classe entidade
#utilizar letra maiúscula no nome de uma classe

class Aluno(models.Model): #representa uma tabela no banco de dados
    
    #matricula é tratada como char pois como inteiro os zeros a esquerda seriam desconsiderados
    #outro motivo é que é uma identificação, não será realizado nenhuma conta
    #unique diz que não podem haver dois valores iguais
    #não é necessário criar um __init__ nessa classe devido a utilização do django que faz isso automatico
    
    matricula = models.CharField(max_length=20, unique=True) 
    nome = models.CharField(max_length=100) 
    senha = models.CharField(max_length=128, blank=True)
    #email

    #cadastro feito pela página inicial (inicio/cadastro.py) fica com aprovado=False até o
    #administrador conferir o documento de confirmação enviado pelo aluno (administrador/views.py).
    #Enquanto não aprovado, a pessoa não consegue entrar. Quem o administrador cadastra
    #pelo /admin/ já nasce aprovado (default=True).
    aprovado = models.BooleanField(default=True)
    cadastrado_em = models.DateTimeField(auto_now_add=True, null=True)
    #documento que comprova o vínculo do aluno (ex.: comprovante de matrícula).
    #Fica guardado em MEDIA_ROOT e só o administrador consegue abrir (administrador/views.py).
    documento_confirmacao = models.FileField(upload_to='documentos_alunos/%Y/%m/', blank=True)

    #expulsão feita pelo administrador. Não apaga a conta (o histórico continua no relatório):
    #só impede o login e esconde a pessoa do sistema. Vazio = conta ativa.
    expulso_em = models.DateTimeField(null=True, blank=True)
    motivo_expulsao = models.CharField(max_length=200, blank=True)

    @property
    def expulso(self):
        return self.expulso_em is not None

    #método chamado quando um print é usado
    def __str__(self):
        return self.nome

