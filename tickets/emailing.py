"""Notificaciones por email de la ticketera.

Usa la misma cuenta SMTP configurada en EmpresaConfig (la que envía las
facturas), pero el destinatario es el contacto de soporte del cliente.
"""
from django.core.mail import EmailMessage
from django.utils import timezone

from arca.models import EmpresaConfig
from arca.mailer import (
    empresa_tiene_email_configurado,
    conexion_smtp,
    mensaje_error_envio,
)

SIN_CUENTA = ("No hay una cuenta de email configurada. Configurala en el panel de "
              "administración (Configuración de la empresa).")


def asunto_ticket(ticket):
    """Asunto fijo: 'Ticket - <empresa> - #<número>'."""
    return f"Ticket - {ticket.cliente.nombre_completo} - {ticket.numero}"


def cuerpo_sugerido(ticket, tipo):
    """Texto sugerido (editable) para la notificación de apertura, cierre o reapertura.
    Si el cierre/reapertura tiene un motivo cargado, se incluye en el cuerpo."""
    saludo = f"Hola {ticket.contacto_nombre}," if ticket.contacto_nombre else "Hola,"

    if tipo == 'cierre':
        cierre = timezone.localtime(ticket.fecha_fin).strftime('%d/%m/%Y a las %H:%M') if ticket.fecha_fin else ''
        motivo = ticket.ultima_nota('CIERRE')
        cuerpo = (
            f"{saludo}\n\n"
            f"Te informamos que el ticket {ticket.numero} «{ticket.titulo}» fue CERRADO"
            f"{f' el {cierre}' if cierre else ''}.\n\n"
        )
        if motivo:
            cuerpo += f"Motivo del cierre:\n{motivo}\n\n"
        cuerpo += (
            f"Detalle original:\n{ticket.descripcion}\n\n"
            f"Ante cualquier duda, quedamos a disposición.\n\n"
            f"Saludos."
        )
        return cuerpo

    if tipo == 'reapertura':
        motivo = ticket.ultima_nota('REAPERTURA')
        cuerpo = (
            f"{saludo}\n\n"
            f"Te informamos que el ticket {ticket.numero} «{ticket.titulo}» fue REABIERTO.\n\n"
        )
        if motivo:
            cuerpo += f"Motivo de la reapertura:\n{motivo}\n\n"
        cuerpo += (
            f"Detalle original:\n{ticket.descripcion}\n\n"
            f"Retomamos el tema y te mantendremos al tanto de su avance.\n\n"
            f"Saludos."
        )
        return cuerpo

    # apertura (default)
    inicio = timezone.localtime(ticket.fecha_inicio).strftime('%d/%m/%Y a las %H:%M') if ticket.fecha_inicio else ''
    return (
        f"{saludo}\n\n"
        f"Se abrió el ticket {ticket.numero} «{ticket.titulo}»"
        f"{f' con fecha {inicio}' if inicio else ''}.\n\n"
        f"Detalle:\n{ticket.descripcion}\n\n"
        f"Te mantendremos al tanto de su avance.\n\n"
        f"Saludos."
    )


def enviar_notificacion_ticket(destinatario, asunto, cuerpo):
    """Envía la notificación del ticket. Devuelve (exito, mensaje)."""
    empresa = EmpresaConfig.get_config()
    if not empresa_tiene_email_configurado(empresa):
        return False, SIN_CUENTA

    connection = conexion_smtp(empresa)
    email = EmailMessage(
        subject=asunto,
        body=cuerpo,
        from_email=empresa.email_from_header(),
        to=[destinatario],
        connection=connection,
    )
    try:
        email.send(fail_silently=False)
        return True, f"Notificación enviada a {destinatario}."
    except Exception as exc:
        return False, mensaje_error_envio(exc, empresa)
