from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0002_ticketevento'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ticket',
            name='fecha_inicio',
            field=models.DateTimeField(auto_now_add=True, verbose_name='Fecha y hora de inicio'),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='fecha_fin',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Fecha y hora de cierre'),
        ),
    ]
