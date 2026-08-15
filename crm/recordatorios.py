"""Recordatorios por email de actividades de CRM vencidas.

Reusa la misma cuenta SMTP configurada en EmpresaConfig (arca/mailer.py,
compartida con facturas/emailing.py y tickets/emailing.py). El destinatario
es el propio dueño de la cuenta (email_remitente): son recordatorios
internos ("tenías que llamar a fulano"), no comunicación con el lead.
"""
from django.core.mail import EmailMessage
from django.utils import timezone

from arca.models import EmpresaConfig
from arca.mailer import empresa_tiene_email_configurado, conexion_smtp

from .models import Actividad


def enviar_recordatorios_vencidos():
    """Manda un email por cada actividad vencida sin recordatorio enviado.
    Best-effort y silencioso: si no hay cuenta configurada, no hace nada.
    Si el envío falla, no se marca recordatorio_enviado, así se reintenta
    en la próxima carga del dashboard (sin propagar el error al usuario)."""
    empresa = EmpresaConfig.get_config()
    if not empresa_tiene_email_configurado(empresa):
        return

    vencidas = Actividad.objects.filter(
        hecha=False, recordatorio_enviado=False, fecha__lt=timezone.localdate(),
    ).select_related('lead')

    if not vencidas:
        return

    connection = conexion_smtp(empresa)
    for actividad in vencidas:
        asunto = f"Recordatorio CRM: {actividad.titulo} — {actividad.lead.nombre}"
        cuerpo = (
            f"Tenías programada esta actividad para el {actividad.fecha:%d/%m/%Y} "
            f"y todavía no la marcaste como hecha.\n\n"
            f"Lead: {actividad.lead.nombre}\n"
            f"Tipo: {actividad.get_tipo_display()}\n"
            f"Título: {actividad.titulo}\n"
        )
        email = EmailMessage(
            subject=asunto, body=cuerpo, from_email=empresa.email_from_header(),
            to=[empresa.email_remitente], connection=connection,
        )
        try:
            email.send(fail_silently=False)
        except Exception:
            continue
        actividad.recordatorio_enviado = True
        actividad.save(update_fields=['recordatorio_enviado'])
