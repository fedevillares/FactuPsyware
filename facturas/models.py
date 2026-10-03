from datetime import date

from django.core.exceptions import ValidationError
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
        ('EMITIENDO', 'Emitiendo (procesando con ARCA)'),
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
    actualizado = models.DateTimeField(
        auto_now=True,
        help_text="Se actualiza sola en cada cambio. Usado para detectar cambios desde otros dispositivos sin recargar la página."
    )

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

    ENTORNOS_EMISION = [
        ('homologacion', 'Homologación'),
        ('produccion', 'Producción'),
    ]
    entorno_emision = models.CharField(
        max_length=20, choices=ENTORNOS_EMISION, blank=True, null=True,
        verbose_name="Entorno de emisión",
        help_text="Se completa automáticamente al pedir el CAE. Permite identificar y borrar facturas de prueba emitidas en homologación."
    )

    # --- Seguimiento interno de cobro y retenciones ---
    # Datos que se cargan DESPUÉS de emitir. No forman parte del comprobante
    # fiscal ni del PDF de ARCA: son solo para el control del cobro dentro de la app.
    pagada = models.BooleanField(default=False, verbose_name="Pagada")
    fecha_pago = models.DateField(blank=True, null=True, verbose_name="Fecha de pago")
    retencion_iva = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name="Retención IVA",
        help_text="Retención de IVA que le practicaron a este comprobante (puede ser 0)."
    )
    retencion_ganancias = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        verbose_name="Retención Ganancias",
        help_text="Retención de Ganancias que le practicaron a este comprobante (puede ser 0)."
    )

    observaciones = models.TextField(
        blank=True, null=True, verbose_name="Notas",
        help_text="Texto libre que se muestra en el comprobante, entre los productos y los totales."
    )
    error_arca = models.TextField(
        blank=True, null=True, verbose_name="Detalle de rechazo de ARCA",
        help_text="Se completa automáticamente si ARCA rechaza el comprobante."
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['entorno_emision', 'punto_venta', 'tipo_comprobante', 'numero'],
                condition=models.Q(numero__isnull=False),
                name='numero_comprobante_unico_por_entorno_pto_vta_y_tipo',
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_comprobante_display()} N° {self.numero or '(sin número)'} - {self.cliente.nombre_completo}"

    @property
    def numero_completo(self):
        if self.numero:
            return f"{self.punto_venta:05d}-{self.numero:08d}"
        return "(sin número)"

    @property
    def nombre_archivo(self):
        """Nombre de archivo único para el PDF: cuit/dni-tipo-puntoventa-numero,
        p.ej. 20266034521-001-00003-00000885. Evita que una Factura A y una B
        con el mismo número se pisen al descargarse."""
        if self.cliente.tipo_documento == '99':
            documento = '9' * 11
        else:
            documento = self.cliente.numero_documento
        tipo = f"{int(self.tipo_comprobante):03d}"
        return f"{documento}-{tipo}-{self.numero_completo}"

    @property
    def letra_comprobante(self):
        letras = {
            '1': 'A', '2': 'A', '3': 'A',
            '6': 'B', '7': 'B', '8': 'B',
            '11': 'C', '12': 'C', '13': 'C',
        }
        return letras.get(self.tipo_comprobante, '')

    @property
    def esta_vencida(self):
        """True si la factura no está pagada y su fecha de vencimiento de pago
        ya pasó. Sirve para marcar en rojo los comprobantes impagos vencidos.
        Las notas de crédito nunca vencen: se autorizan y se saldan en el momento."""
        if self.es_nota_credito or self.pagada or not self.fecha_vto_pago:
            return False
        return self.fecha_vto_pago < date.today()

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
        comprobante el desglose que exige ARCA (IVA 27%/21%/10.5%/5%/2.5%/0%).
        Siempre lista las seis alícuotas (con importe 0 si no se usó
        ninguna), igual que el layout oficial de ARCA."""
        porcentajes = {'3': 0, '4': 10.5, '5': 21, '6': 27, '8': 5, '9': 2.5}
        agrupado = {clave: 0 for clave in porcentajes}
        for item in self.items.all():
            agrupado[item.alicuota_iva] += item.iva_monto
        return [
            {'porcentaje': porcentajes[clave], 'importe': importe}
            for clave, importe in sorted(agrupado.items(), key=lambda kv: porcentajes[kv[0]], reverse=True)
        ]


class FacturaItem(models.Model):
    factura = models.ForeignKey(Factura, on_delete=models.CASCADE, related_name='items')
    servicio = models.ForeignKey(
        Servicio, on_delete=models.PROTECT, blank=True, null=True,
        help_text="Dejalo vacío para cargar un producto personalizado (completá el nombre en "
        "'Descripción personalizada' y el precio a mano)."
    )
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
    descripcion_personalizada = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name="Descripción personalizada",
        help_text="Si elegiste un Servicio, reemplaza su nombre solo en esta línea sin modificar el catálogo. "
        "Si no elegiste ningún Servicio, este es el nombre del producto personalizado."
    )

    def clean(self):
        super().clean()
        if not self.servicio_id and not self.descripcion_personalizada:
            raise ValidationError({
                'descripcion_personalizada': "Si no elegís un Servicio del catálogo, "
                "completá este campo con el nombre del producto personalizado."
            })

    @property
    def nombre_mostrado(self):
        return self.descripcion_personalizada or (self.servicio.nombre if self.servicio_id else "")

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

    class Meta:
        verbose_name = "Línea de factura"
        verbose_name_plural = "Líneas de factura"

    def __str__(self):
        return f"{self.nombre_mostrado} x{self.cantidad}"
