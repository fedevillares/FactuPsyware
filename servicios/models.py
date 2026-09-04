from django.db import models


class Servicio(models.Model):
    ALICUOTAS_IVA = [
        ('3', '0%'),
        ('4', '10.5%'),
        ('5', '21%'),
        ('6', '27%'),
        ('8', '5%'),
        ('9', '2.5%'),
    ]

    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, null=True)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    alicuota_iva = models.CharField(max_length=2, choices=ALICUOTAS_IVA, default='5')  # 21% por defecto
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

    @property
    def precio_con_iva(self):
        porcentajes = {'3': 0, '4': 10.5, '5': 21, '6': 27, '8': 5, '9': 2.5}
        porcentaje = porcentajes[self.alicuota_iva]
        return round(float(self.precio_unitario) * (1 + porcentaje / 100), 2)