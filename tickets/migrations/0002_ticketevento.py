import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tickets', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TicketEvento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[('CIERRE', 'Cierre'), ('REAPERTURA', 'Reapertura')], max_length=12)),
                ('nota', models.TextField(blank=True, verbose_name='Motivo / nota')),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('ticket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='eventos', to='tickets.ticket')),
            ],
            options={
                'verbose_name': 'Evento de ticket',
                'verbose_name_plural': 'Eventos de ticket',
                'ordering': ['-fecha'],
            },
        ),
    ]
