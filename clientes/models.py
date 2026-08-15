from django.db import models

class Cliente(models.Model):
    TIPO_DOCUMENTO = [
        ('80', 'CUIT'),
        ('86', 'CUIL'),
        ('96', 'DNI'),
        ('87', 'CDI'),
        ('99', 'Consumidor Final (Sin identificar)'),
    ]

    CONDICION_IVA = [
        ('RI', 'Responsable Inscripto'),
        ('MONO', 'Monotributista'),
        ('EX', 'Exento'),
        ('CF', 'Consumidor Final'),
    ]

    nombre_completo = models.CharField(max_length=200)
    tipo_documento = models.CharField(max_length=2, choices=TIPO_DOCUMENTO, default='96')
    numero_documento = models.CharField(max_length=20, unique=True)
    telefono = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    condicion_iva = models.CharField(max_length=4, choices=CONDICION_IVA, default='CF')
    fecha_alta = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre_completo} ({self.get_tipo_documento_display()}: {self.numero_documento})"