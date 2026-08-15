from django.db import models
from clientes.models import Cliente
from servicios.models import Servicio


class Factura(models.Model):
    TIPO_COMPROBANTE = [
        ('1', 'Factura A'),
        ('6', 'Factura B'),
        ('11', 'Factura C'),
        ('2', 'Nota de Débito A'),
        ('7', 'Nota de Débito B'),
        ('12', 'Nota de Débito C'),
        ('3', 'Nota de Crédito A'),
        ('8', 'Nota de Crédito B'),
        ('13', 'Nota de Crédito C'),
    ]

    ESTADOS = [
        ('BORRADOR', 'Borrador'),
        ('AUTORIZADA', 'Autorizada (con CAE)'),
        ('ERROR', 'Error al autorizar'),
    ]

    CONDICIONES_VENTA = [
        ('CONTADO', 'Contado'),
        ('TRANSFERENCIA', 'Transferencia Bancaria'),
        ('CUENTA_CORRIENTE', 'Cuenta Corriente'),
        ('TARJETA', 'Tarjeta'),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='facturas')
    tipo_comprobante = models.CharField(max_length=2, choices=TIPO_COMPROBANTE, default='6')
    punto_venta = models.IntegerField(default=1)
    numero = models.IntegerField(blank=True, null=True)
    fecha_emision = models.DateField(auto_now_add=True)

    factura_asociada = models.ForeignKey(
        'self', on_delete=models.PROTECT, blank=True, null=True,
        related_name='notas_relacionadas',
        verbose_name="Comprobante asociado (para Notas de Crédito/Débito)"
    )

    periodo_desde = models.DateField(blank=True, null=True, verbose_name="Período facturado desde")
    periodo_hasta = models.DateField(blank=True, null=True, verbose_name="Período facturado hasta")
    fecha_vto_pago = models.DateField(blank=True, null=True, verbose_name="Fecha de vencimiento para el pago")
    condicion_venta = models.CharField(max_length=20, choices=CONDICIONES_VENTA, default='TRANSFERENCIA')

    estado = models.CharField(max_length=10, choices=ESTADOS, default='BORRADOR')
    cae = models.CharField(max_length=20, blank=True, null=True)
    cae_vencimiento = models.DateField(blank=True, null=True)

    observaciones = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.get_tipo_comprobante_display()} N° {self.numero or '(sin número)'} - {self.cliente.nombre_completo}"

    @property
    def numero_completo(self):
        if self.numero:
            return f"{self.punto_venta:05d}-{self.numero:08d}"
        return "(sin número)"

    @property
    def es_nota_credito(self):
        return self.tipo_comprobante in ('3', '8', '13')

    @property
    def es_nota_debito(self):
        return self.tipo_comprobante in ('2', '7', '12')

    @property
    def subtotal(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def total_iva(self):
        return sum(item.iva_monto for item in self.items.all())

    @property
    def total(self):
        return self.subtotal + self.total_iva

    @property
    def desglose_iva(self):
        """Agrupa el IVA de los items por alícuota, para mostrar en el
        comprobante el desglose que exige ARCA (IVA 27%/21%/10.5%/5%/2.5%/0%)."""
        porcentajes = {'3': 0, '4': 10.5, '5': 21, '6': 27, '8': 5, '9': 2.5}
        agrupado = {}
        for item in self.items.all():
            clave = item.alicuota_iva
            if clave not in agrupado:
                agrupado[clave] = 0
            agrupado[clave] += item.iva_monto
        return [
            {'porcentaje': porcentajes[clave], 'importe': importe}
            for clave, importe in sorted(agrupado.items(), key=lambda kv: porcentajes[kv[0]], reverse=True)
        ]


class FacturaItem(models.Model):
    factura = models.ForeignKey(Factura, on_delete=models.CASCADE, related_name='items')
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    alicuota_iva = models.CharField(max_length=2, choices=[
        ('3', '0%'),
        ('4', '10.5%'),
        ('5', '21%'),
        ('6', '27%'),
        ('8', '5%'),
        ('9', '2.5%'),
    ])

    @property
    def subtotal(self):
        return float(self.cantidad) * float(self.precio_unitario)

    @property
    def iva_monto(self):
        porcentajes = {'3': 0, '4': 10.5, '5': 21, '6': 27, '8': 5, '9': 2.5}
        porcentaje = porcentajes[self.alicuota_iva]
        return round(self.subtotal * porcentaje / 100, 2)

    @property
    def total(self):
        return self.subtotal + self.iva_monto

    def __str__(self):
        return f"{self.servicio.nombre} x{self.cantidad}"
