from django.db import models

from alunos.models import Aluno
from monitor.models import Monitor


class Denuncia(models.Model):
    """
    Um monitor denuncia um aluno (faltou sem avisar, foi desrespeitoso...).

    A denúncia vai para o administrador, que decide: expulsar o aluno (com a expulsão que já
    existe, em administrador/usuarios.py) ou arquivar. Ela continua guardada depois de
    resolvida, para o histórico do aluno.
    """
    PENDENTE = 'pendente'
    EXPULSO = 'expulso'
    ARQUIVADA = 'arquivada'
    SITUACOES = [(PENDENTE, 'Pendente'), (EXPULSO, 'Aluno expulso'), (ARQUIVADA, 'Arquivada')]

    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE, related_name='denuncias')
    #SET_NULL: se o monitor for apagado, a denúncia continua (sem o nome de quem fez)
    monitor = models.ForeignKey(Monitor, on_delete=models.SET_NULL, null=True, related_name='denuncias_feitas')
    motivo = models.TextField(max_length=500)
    criada_em = models.DateTimeField(auto_now_add=True)
    situacao = models.CharField(max_length=10, choices=SITUACOES, default=PENDENTE)
    resolvida_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-criada_em']

    @property
    def pendente(self):
        return self.situacao == self.PENDENTE

    def __str__(self):
        return f'{self.monitor or "Monitor apagado"} denunciou {self.aluno} em {self.criada_em:%d/%m/%Y}'
