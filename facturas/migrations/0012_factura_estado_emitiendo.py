from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('facturas', '0011_ayuda_producto_personalizado'),
    ]

    operations = [
        migrations.AlterField(
            model_name='factura',
            name='estado',
            field=models.CharField(choices=[('BORRADOR', 'Borrador'), ('EMITIENDO', 'Emitiendo (procesando con ARCA)'), ('AUTORIZADA', 'Autorizada (con CAE)'), ('ERROR', 'Error al autorizar')], default='BORRADOR', max_length=10),
        ),
    ]
