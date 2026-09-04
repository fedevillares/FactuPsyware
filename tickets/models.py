from django.db import models

from clientes.models import Cliente


class Ticket(models.Model):
    ESTADOS = [
        ('PENDIENTE', 'Pendiente'),
        ('CERRADO', 'Cerrado'),
    ]

    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name='tickets',
        verbose_name="Empresa / cliente"
    )
    titulo = models.CharField(max_length=200, verbose_name="Título")
    descripcion = models.TextField(verbose_name="Descripción")

    # Contacto técnico del ticket. Se autocompleta desde el cliente al crear,
    # pero queda guardado por si el contacto de la empresa cambia después.
    contacto_nombre = models.CharField(max_length=200, blank=True, verbose_name="Contacto técnico")
    contacto_email = models.EmailField(blank=True, verbose_name="Email del contacto")

    estado = models.CharField(max_length=10, choices=ESTADOS, default='PENDIENTE')
    fecha_inicio = models.DateTimeField(auto_now_add=True, verbose_name="Fecha y hora de inicio")
    fecha_fin = models.DateTimeField(blank=True, null=True, verbose_name="Fecha y hora de cierre")
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-creado']
        verbose_name = "Ticket"
        verbose_name_plural = "Tickets"

    def __str__(self):
        return f"{self.numero} — {self.titulo}"

    @property
    def numero(self):
        """Número visible del ticket, correlativo, ej. '#0001'."""
        return f"#{self.id:04d}" if self.id else "#—"

    @property
    def esta_cerrado(self):
        return self.estado == 'CERRADO'

    def ultima_nota(self, tipo):
        """Nota del último evento (cierre/reapertura) del tipo pedido, o ''."""
        evento = self.eventos.filter(tipo=tipo).first()
        return evento.nota if evento else ''


class TicketEvento(models.Model):
    """Registro de cada cierre o reapertura de un ticket, con el motivo.

    Se guarda como historial (un ticket puede cerrarse y reabrirse varias
    veces) y el motivo se usa para armar el email de notificación."""
    TIPOS = [
        ('CIERRE', 'Cierre'),
        ('REAPERTURA', 'Reapertura'),
    ]

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name='eventos'
    )
    tipo = models.CharField(max_length=12, choices=TIPOS)
    nota = models.TextField(blank=True, verbose_name="Motivo / nota")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = "Evento de ticket"
        verbose_name_plural = "Eventos de ticket"

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.ticket.numero}"
