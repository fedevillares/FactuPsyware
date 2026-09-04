import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('clientes', '0003_cliente_contacto_soporte'),
    ]

    operations = [
        migrations.CreateModel(
            name='Ticket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titulo', models.CharField(max_length=200, verbose_name='Título')),
                ('descripcion', models.TextField(verbose_name='Descripción')),
                ('contacto_nombre', models.CharField(blank=True, max_length=200, verbose_name='Contacto técnico')),
                ('contacto_email', models.EmailField(blank=True, max_length=254, verbose_name='Email del contacto')),
                ('estado', models.CharField(choices=[('PENDIENTE', 'Pendiente'), ('CERRADO', 'Cerrado')], default='PENDIENTE', max_length=10)),
                ('fecha_inicio', models.DateField(auto_now_add=True, verbose_name='Fecha de inicio')),
                ('fecha_fin', models.DateField(blank=True, null=True, verbose_name='Fecha de cierre')),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('cliente', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tickets', to='clientes.cliente', verbose_name='Empresa / cliente')),
            ],
            options={
                'verbose_name': 'Ticket',
                'verbose_name_plural': 'Tickets',
                'ordering': ['-creado'],
            },
        ),
    ]
