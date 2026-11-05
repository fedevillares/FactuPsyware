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

    # ── Cuenta de soporte (ticketera) ──────────────────────────────────────
    # Cuenta propia para los tickets: envía las notificaciones y además se
    # revisa por IMAP para abrir tickets automáticamente a partir de los
    # correos con asunto "TICKET DE SOPORTE" (ver tickets/correo_entrante.py).
    # Si soporte_email queda vacío, se usa la cuenta de facturas de arriba.
    soporte_nombre_remitente = models.CharField(max_length=100, blank=True, default='', verbose_name="Nombre del remitente (soporte)", help_text="Nombre visible en los emails de tickets (ej. 'Soporte Psyware'). Si está vacío, se usa el de facturas o la Razón Social")
    soporte_email = models.EmailField(blank=True, default='', verbose_name="Email de soporte", help_text="Cuenta que envía los emails de tickets y recibe los pedidos de soporte. Si está vacío, se usa la cuenta de facturas")
    soporte_password = models.CharField(max_length=512, blank=True, default='', verbose_name="Contraseña / clave de aplicación (soporte)", help_text="Se guarda cifrada.")
    soporte_smtp_host = models.CharField(max_length=255, blank=True, default='smtp.gmail.com', verbose_name="Servidor SMTP (soporte)", help_text="Gmail: smtp.gmail.com. Dominio propio en un hosting: el servidor del hosting (ej. mail.tudominio.com)")
    soporte_smtp_port = models.IntegerField(blank=True, null=True, default=587, verbose_name="Puerto SMTP (soporte)", help_text="587 = TLS (STARTTLS). 465 = SSL directo (se detecta solo por el puerto)")
    soporte_smtp_tls = models.BooleanField(default=True, verbose_name="Usar TLS (soporte)")
    soporte_imap_host = models.CharField(max_length=255, blank=True, default='imap.gmail.com', verbose_name="Servidor IMAP (recepción)", help_text="Gmail: imap.gmail.com. Dominio propio en un hosting: el servidor del hosting (ej. mail.tudominio.com)")
    soporte_imap_port = models.IntegerField(blank=True, null=True, default=993, verbose_name="Puerto IMAP (SSL)")
    soporte_recepcion_activa = models.BooleanField(default=False, verbose_name="Abrir tickets automáticamente desde el correo", help_text="Revisa la bandeja de entrada cada minuto. Solo se abren tickets de correos enviados desde el 'Email de soporte' de algún cliente y con asunto 'TICKET DE SOPORTE'. Para Gmail hay que tener IMAP habilitado.")

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

    def cuenta_soporte(self):
        """Cuenta de correo a usar para la ticketera (envío y recepción).
        Si no se cargó una cuenta de soporte propia, cae en la de facturas."""
        from .crypto import descifrar
        from .mailer import CuentaCorreo
        if self.soporte_email:
            return CuentaCorreo(
                usuario=self.soporte_email,
                password=descifrar(self.soporte_password),
                nombre=self.soporte_nombre_remitente or self.email_nombre_remitente or self.razon_social,
                smtp_host=self.soporte_smtp_host or 'smtp.gmail.com',
                smtp_port=self.soporte_smtp_port or 587,
                smtp_tls=self.soporte_smtp_tls,
                imap_host=self.soporte_imap_host or 'imap.gmail.com',
                imap_port=self.soporte_imap_port or 993,
            )
        return CuentaCorreo(
            usuario=self.email_remitente or '',
            password=self.email_password_plano,
            nombre=self.soporte_nombre_remitente or self.email_nombre_remitente or self.razon_social,
            smtp_host=self.email_host,
            smtp_port=self.email_port,
            smtp_tls=self.email_use_tls,
            imap_host=self.soporte_imap_host or 'imap.gmail.com',
            imap_port=self.soporte_imap_port or 993,
        )

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