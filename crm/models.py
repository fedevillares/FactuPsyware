from datetime import date

from django.db import models

from clientes.models import Cliente


class Lead(models.Model):
    ORIGENES = [
        ('REFERIDO', 'Referido'),
        ('REDES', 'Redes sociales'),
        ('WEB', 'Web'),
        ('OTRO', 'Otro'),
    ]

    ESTADOS = [
        ('NUEVO', 'Nuevo'),
        ('CONTACTADO', 'Contactado'),
        ('NEGOCIACION', 'En negociación'),
        ('GANADO', 'Ganado'),
        ('PERDIDO', 'Perdido'),
    ]

    nombre = models.CharField(max_length=200)
    telefono = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    origen = models.CharField(max_length=10, choices=ORIGENES, default='OTRO')
    estado = models.CharField(max_length=12, choices=ESTADOS, default='NUEVO')
    proximo_contacto = models.DateField(blank=True, null=True, verbose_name="Próximo contacto")

    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, blank=True, null=True,
        related_name='leads',
        verbose_name="Cliente (una vez convertido)",
        help_text="Se completa solo al convertir el lead en Cliente.",
    )

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(
        auto_now=True,
        help_text="Se actualiza sola en cada cambio.",
    )

    class Meta:
        ordering = ['-actualizado']
        verbose_name = "Lead"
        verbose_name_plural = "Leads"

    def __str__(self):
        return self.nombre

    @property
    def esta_ganado(self):
        return self.estado == 'GANADO'


class NotaLead(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='notas')
    texto = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = "Nota de lead"
        verbose_name_plural = "Notas de lead"

    def __str__(self):
        return f"Nota de {self.lead.nombre} — {self.fecha:%d/%m/%Y}"


class Actividad(models.Model):
    TIPOS = [
        ('NOTA', 'Nota'),
        ('LLAMADA', 'Llamada'),
        ('REUNION', 'Reunión'),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='actividades')
    tipo = models.CharField(max_length=10, choices=TIPOS, default='NOTA')
    titulo = models.CharField(max_length=200)
    fecha = models.DateField(verbose_name="Fecha", help_text="Cuándo pasó (si ya está hecha) o cuándo vence (si no).")
    hecha = models.BooleanField(default=False, verbose_name="Hecha")
    recordatorio_enviado = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-creado']
        verbose_name = "Actividad"
        verbose_name_plural = "Actividades"

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.titulo}"

    @property
    def esta_vencida(self):
        return not self.hecha and self.fecha < date.today()
