from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('facturas', '0013_remove_factura_numero_comprobante_unico_por_pto_vta_y_tipo_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='factura',
            name='pagada',
            field=models.BooleanField(default=False, verbose_name='Pagada'),
        ),
        migrations.AddField(
            model_name='factura',
            name='fecha_pago',
            field=models.DateField(blank=True, null=True, verbose_name='Fecha de pago'),
        ),
        migrations.AddField(
            model_name='factura',
            name='retencion_iva',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Retención de IVA que le practicaron a este comprobante (puede ser 0).', max_digits=12, verbose_name='Retención IVA'),
        ),
        migrations.AddField(
            model_name='factura',
            name='retencion_ganancias',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Retención de Ganancias que le practicaron a este comprobante (puede ser 0).', max_digits=12, verbose_name='Retención Ganancias'),
        ),
    ]
