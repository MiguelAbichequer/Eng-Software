from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0002_disciplina_monitor_disciplinas_horario_solicitacao'),
    ]

    operations = [
        migrations.AddField(
            model_name='monitor',
            name='senha',
            field=models.CharField(blank=True, max_length=128),
        ),
    ]
