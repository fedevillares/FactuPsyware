from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0002_rename_dni_cliente_numero_documento_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='contacto_soporte_nombre',
            field=models.CharField(blank=True, help_text='Persona encargada del soporte técnico en esta empresa (para la ticketera).', max_length=200, null=True, verbose_name='Contacto de soporte'),
        ),
        migrations.AddField(
            model_name='cliente',
            name='contacto_soporte_email',
            field=models.EmailField(blank=True, help_text='Email al que se notifican las aperturas y cierres de tickets. No es el email general del cliente.', max_length=254, null=True, verbose_name='Email de soporte'),
        ),
    ]
