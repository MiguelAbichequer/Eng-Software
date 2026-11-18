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
    senha = models.CharField(max_length=128, blank=True) #guardada com hash (make_password), igual ao aluno
    disciplinas = models.ManyToManyField(Disciplina, blank=True, related_name='monitores')

    #o status é o monitor quem escolhe, no painel dele: quando chega um aluno ele marca
    #"em atendimento", quando o aluno sai volta para "disponível", e quando precisa se ausentar
    #marca "indisponível". Não depende dos horários cadastrados. Ao clicar em Sair, volta
    #sozinho para "indisponível" (inicio/views.py), para ele não ficar disponível sem estar lá.
    DISPONIVEL = 'disponivel'
    EM_ATENDIMENTO = 'em_atendimento'
    INDISPONIVEL = 'indisponivel'
    STATUS = [(DISPONIVEL, 'Disponível'), (EM_ATENDIMENTO, 'Em atendimento'), (INDISPONIVEL, 'Indisponível')]
    status = models.CharField(max_length=14, choices=STATUS, default=INDISPONIVEL)

    #aprovação pelo administrador: quem se cadastra pela página inicial fica com
    #aprovado=False e não consegue entrar nem aparece para os alunos até o administrador
    #aprovar (administrador/views.py). Quem o administrador cadastra pelo /admin/ já nasce aprovado.
    aprovado = models.BooleanField(default=True)
    cadastrado_em = models.DateTimeField(auto_now_add=True, null=True)

    #expulsão feita pelo administrador. Não apaga a conta (o histórico continua no relatório):
    #só impede o login e esconde a pessoa do sistema. Vazio = conta ativa.
    expulso_em = models.DateTimeField(null=True, blank=True)
    motivo_expulsao = models.CharField(max_length=200, blank=True)

    @property
    def expulso(self):
        return self.expulso_em is not None

    def __str__(self):
        return self.nome

#tamanho de cada "bloco" que o aluno reserva dentro de um horário
MINUTOS_BLOCO = 15


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

        #o aluno reserva em blocos de 15 minutos, então o horário precisa começar e
        #terminar em um múltiplo de 15 (14:00, 14:15, 14:30, 14:45)
        for hora in (self.hora_inicio, self.hora_fim):
            if hora and (hora.minute % MINUTOS_BLOCO or hora.second):
                raise ValidationError(
                    f'Use horários em múltiplos de {MINUTOS_BLOCO} minutos (por exemplo, 14:00, 14:15, 14:30 ou 14:45).'
                )

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

    def __str__(self):
        return f"{self.monitor} - {self.get_dia_semana_display()} {self.hora_inicio:%H:%M}-{self.hora_fim:%H:%M}"


class Solicitacao(models.Model):
    FORMATOS = [('online', 'Online'), ('presencial', 'Presencial')]
    PARTICIPANTES = [('individual', 'Individual'), ('grupo', 'Em grupo')]

    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE, related_name='solicitacoes')
    horario = models.ForeignKey(Horario, on_delete=models.CASCADE, related_name='solicitacoes')
    data = models.DateField()
    #o trecho reservado dentro do horário: um ou mais blocos de 15 minutos seguidos
    #(ex.: horário 14:00-16:00, reserva 14:30-15:00 = dois blocos)
    hora_inicio = models.TimeField()
    hora_fim = models.TimeField()
    assunto = models.CharField(max_length=200)
    formato = models.CharField(max_length=10, choices=FORMATOS)
    participantes = models.CharField(max_length=10, choices=PARTICIPANTES)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        #não há restrição de unicidade aqui: duas reservas não podem se sobrepor no mesmo
        #horário e data, mas isso é uma regra de intervalos (14:00-14:30 x 14:15-14:45),
        #que o banco não confere sozinho. Quem garante é interface_aluno/reservas.py,
        #que trava o horário durante a reserva para dois alunos não pegarem o mesmo bloco.
        ordering = ['data', 'hora_inicio']

    def __str__(self):
        return f"{self.aluno} -> {self.horario.monitor} em {self.data:%d/%m/%Y}, {self.hora_inicio:%H:%M}-{self.hora_fim:%H:%M}"
