"""
Status escolhido pelo monitor.

Sai o status manual temporário (status_manual + status_manual_ate) e entra um campo
"status" com três valores (disponível, em atendimento, indisponível), que só o monitor muda.
Todos os monitores começam "indisponível".
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0006_varios_alunos_por_horario'),
    ]

    operations = [
        migrations.RemoveField(model_name='monitor', name='status_manual'),
        migrations.RemoveField(model_name='monitor', name='status_manual_ate'),
        migrations.AddField(
            model_name='monitor',
            name='status',
            field=models.CharField(
                choices=[('disponivel', 'Disponível'), ('em_atendimento', 'Em atendimento'), ('indisponivel', 'Indisponível')],
                default='indisponivel', max_length=14,
            ),
        ),
    ]
