"""
Reserva em blocos de 15 minutos.

Solicitacao ganha hora_inicio e hora_fim (o trecho reservado dentro do horário) e perde a
restrição "um aluno por horário e data": agora o mesmo aluno pode ter duas reservas
separadas no mesmo horário (ex.: 14:00-14:15 e 14:45-15:00).

As reservas que já existiam reservavam o horário inteiro, então recebem o início e o fim do
próprio horário. Os campos são criados vazios, preenchidos e só depois ficam obrigatórios.
"""

from django.db import migrations, models


def preencher_trecho(apps, schema_editor):
    Solicitacao = apps.get_model('monitor', 'Solicitacao')
    for s in Solicitacao.objects.select_related('horario'):
        s.hora_inicio = s.horario.hora_inicio
        s.hora_fim = s.horario.hora_fim
        s.save(update_fields=['hora_inicio', 'hora_fim'])


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0007_status_do_monitor'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='solicitacao',
            name='uma_solicitacao_por_aluno_horario_e_data',
        ),
        migrations.AddField(model_name='solicitacao', name='hora_inicio', field=models.TimeField(null=True)),
        migrations.AddField(model_name='solicitacao', name='hora_fim', field=models.TimeField(null=True)),
        migrations.RunPython(preencher_trecho, migrations.RunPython.noop),
        migrations.AlterField(model_name='solicitacao', name='hora_inicio', field=models.TimeField()),
        migrations.AlterField(model_name='solicitacao', name='hora_fim', field=models.TimeField()),
        migrations.AlterModelOptions(name='solicitacao', options={'ordering': ['data', 'hora_inicio']}),
    ]
