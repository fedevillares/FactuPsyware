from django.db import models


class EmpresaConfig(models.Model):
    razon_social = models.CharField(max_length=200)
    cuit = models.CharField(max_length=20)
    ingresos_brutos = models.CharField(max_length=50, blank=True, null=True)
    domicilio = models.CharField(max_length=255)
    localidad = models.CharField(max_length=100)
    telefono = models.CharField(max_length=50, blank=True, null=True)
    inicio_actividades = models.DateField(blank=True, null=True)
    condicion_iva = models.CharField(max_length=50, default='IVA Responsable Inscripto')
    punto_venta_defecto = models.IntegerField(default=1)
    otros_impuestos_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Porcentaje estimado de otros impuestos nacionales indirectos contenidos en el precio (Ley 27.743)")
    leyenda = models.CharField(max_length=255, blank=True, null=True, help_text="Frase descriptiva que aparece al pie del comprobante")

    class Meta:
        verbose_name = "Configuración de la empresa"
        verbose_name_plural = "Configuración de la empresa"

    def __str__(self):
        return self.razon_social

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls):
        config, _ = cls.objects.get_or_create(pk=1, defaults={
            'razon_social': 'Mi Empresa',
            'cuit': '20000000000',
            'domicilio': '',
            'localidad': '',
        })
        return config