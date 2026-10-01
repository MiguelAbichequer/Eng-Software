# """exemplo""" - string usada para documentar classes
#app alunos que o django fará a comunicação do python com o mysql

#arquivo models é utilizado para definir as classes que serão transformadas em tabelas pelo django
#Model é o comando que diz ao django que deve tratar o dado como um modelo de dados

from django.db import models

#classe entidade
#utilizar letra maiúscula no nome de uma classe

class Monitor(models.Model): #representa uma tabela no banco de dados
    
    #matricula é tratada como char pois como inteiro os zeros a esquerda seriam desconsiderados
    #outro motivo é que é uma identificação, não será realizado nenhuma conta
    #unique diz que não podem haver dois valores iguais
    #não é necessário criar um __init__ nessa classe devido a utilização do django que faz isso automatico
    
    matricula = models.CharField(max_length=20, unique=True) 
    nome = models.CharField(max_length=100) 
    #email

    #método chamado quando um print é usado
    def __str__(self):
        return self.nome


