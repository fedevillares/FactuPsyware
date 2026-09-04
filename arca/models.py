from django.db import models

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

LOGO_TAMANO_MAXIMO_MB = 5


def validar_tamano_logo(value):
    if value.size > LOGO_TAMANO_MAXIMO_MB * 1024 * 1024:
        raise ValidationError(f"El logo no puede superar los {LOGO_TAMANO_MAXIMO_MB} MB.")


class EmpresaConfig(models.Model):
    logo = models.ImageField(
        upload_to='empresa/', blank=True, null=True,
        verbose_name="Logo",
        help_text="Tamaño sugerido: 400×160 px (relación 2.5:1), PNG con fondo transparente, para que se vea nítido en el comprobante impreso. Máx. 5 MB.",
        validators=[
            FileExtensionValidator(allowed_extensions=['png', 'jpg', 'jpeg', 'webp']),
            validar_tamano_logo,
        ],
    )
    nombre_fantasia = models.CharField(max_length=200, blank=True, help_text="Nombre comercial/marca que se muestra como título del comprobante (si está vacío, se usa la Razón Social)")
    razon_social = models.CharField(max_length=200, help_text="Razón Social legal, tal como figura ante ARCA")
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

    email_nombre_remitente = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nombre del remitente", help_text="Nombre que va a ver el cliente como remitente del email (ej. 'Lic. Fernando Villares'). Si está vacío, se usa la Razón Social")
    email_remitente = models.EmailField(blank=True, null=True, verbose_name="Email remitente", help_text="Cuenta desde la que se envían las facturas por email (ej. Gmail)")
    email_password = models.CharField(max_length=512, blank=True, null=True, verbose_name="Contraseña / clave de aplicación", help_text="Para Gmail, usar una 'contraseña de aplicación', no la contraseña normal de la cuenta. Se guarda cifrada.")
    email_host = models.CharField(max_length=255, blank=True, null=True, default='smtp.gmail.com', verbose_name="Servidor SMTP")
    email_port = models.IntegerField(blank=True, null=True, default=587, verbose_name="Puerto SMTP")
    email_use_tls = models.BooleanField(default=True, verbose_name="Usar TLS")

    class Meta:
        verbose_name = "Configuración de la empresa"
        verbose_name_plural = "Configuración de la empresa"

    def __str__(self):
        return self.razon_social

    def email_from_header(self):
        """Devuelve el remitente con nombre visible, ej. 'Fernando Villares <cuenta@gmail.com>'."""
        nombre = self.email_nombre_remitente or self.razon_social
        return f"{nombre} <{self.email_remitente}>"

    @property
    def email_password_plano(self):
        """Descifra email_password para usarlo al conectar por SMTP
        (arca/mailer.py). Nunca usar email_password directo fuera de este
        modulo: siempre esta cifrado en la base."""
        from .crypto import descifrar
        return descifrar(self.email_password)

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