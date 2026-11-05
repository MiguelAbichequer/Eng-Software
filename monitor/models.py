# """exemplo""" - string usada para documentar classes
#app alunos que o django fará a comunicação do python com o mysql

#arquivo models é utilizado para definir as classes que serão transformadas em tabelas pelo django
#Model é o comando que diz ao django que deve tratar o dado como um modelo de dados

from django.core.exceptions import ValidationError
from django.db import models

from alunos.models import Aluno

#classe entidade
#utilizar letra maiúscula no nome de uma classe

class Disciplina(models.Model):
    codigo = models.CharField(max_length=20, unique=True)
    nome = models.CharField(max_length=100)

    def __str__(self):
        return self.nome

class Monitor(models.Model): #representa uma tabela no banco de dados
    
    #matricula é tratada como char pois como inteiro os zeros a esquerda seriam desconsiderados
    #outro motivo é que é uma identificação, não será realizado nenhuma conta
    #unique diz que não podem haver dois valores iguais
    #não é necessário criar um __init__ nessa classe devido a utilização do django que faz isso automatico
    
    matricula = models.CharField(max_length=20, unique=True)
    nome = models.CharField(max_length=100)

    nome = models.CharField(max_length=100)
    senha = models.CharField(max_length=128, blank=True) #guardada com hash (make_password), igual ao aluno
    disciplinas = models.ManyToManyField(Disciplina, blank=True, related_name='monitores')

    disciplinas = models.ManyToManyField(Disciplina, blank=True, related_name='monitores')

    def __str__(self):
        return self.nome

class DiasSemana(models.IntegerChoices): # permite criar uma enumeração, relacionando dias com números.
    SEGUNDA = 0, "Segunda-feira"
    TERCA   = 1, "Terça-feira"
    QUARTA  = 2, "Quarta-feira"
    QUINTA  = 3, "Quinta-feira"
    SEXTA   = 4, "Sexta-feira"
    SABADO  = 5, "Sábado"
    DOMINGO = 6, "Domingo"

class Horario(models.Model):
    monitor = models.ForeignKey(Monitor, on_delete=models.CASCADE, related_name='horarios')
    dia_semana = models.IntegerField(choices=DiasSemana.choices)
    hora_inicio = models.TimeField()
    hora_fim = models.TimeField()

    class Meta:
        ordering = ['dia_semana', 'hora_inicio']

    def clean(self):
        if self.hora_inicio and self.hora_fim and self.hora_fim <= self.hora_inicio:
            raise ValidationError('O horário final deve ser depois do inicial.')

        # não deve haver sobreposição de horários para o mesmo monitor no mesmo dia da semana
        # (dois intervalos se sobrepõem quando cada um começa antes de o outro terminar)
        if self.monitor_id and self.hora_inicio and self.hora_fim:
            conflitos = Horario.objects.filter(
                monitor_id=self.monitor_id,
                dia_semana=self.dia_semana,
                hora_inicio__lt=self.hora_fim,
                hora_fim__gt=self.hora_inicio,
            ).exclude(pk=self.pk)
            if conflitos.exists():
                raise ValidationError('Esse horário se sobrepõe a outro já cadastrado para o mesmo dia.')
        # não deve haver sobreposição de horários para o mesmo monitor no mesmo dia da semana
    def __str__(self):
        return f"{self.monitor} - {self.get_dia_semana_display()} {self.hora_inicio:%H:%M}-{self.hora_fim:%H:%M}"


class Solicitacao(models.Model):
    FORMATOS = [('online', 'Online'), ('presencial', 'Presencial')]
    PARTICIPANTES = [('individual', 'Individual'), ('grupo', 'Em grupo')]

    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE, related_name='solicitacoes')
    horario = models.ForeignKey(Horario, on_delete=models.CASCADE, related_name='solicitacoes')
    data = models.DateField()
    assunto = models.CharField(max_length=200)
    formato = models.CharField(max_length=10, choices=FORMATOS)
    participantes = models.CharField(max_length=10, choices=PARTICIPANTES)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['horario', 'data'], name='uma_solicitacao_por_horario_e_data'),
        ]

    def __str__(self):
        return f"{self.aluno} -> {self.horario} em {self.data:%d/%m/%Y}"
