"""Notificaciones por email de la ticketera.

Usa la cuenta de soporte de EmpresaConfig (`cuenta_soporte()`); si no se
cargó una cuenta de soporte propia, cae en la cuenta de facturas. El
destinatario es el contacto de soporte del cliente.
"""
from django.core.mail import EmailMessage
from django.utils import timezone

from arca.models import EmpresaConfig
from arca.mailer import conexion_smtp_cuenta, mensaje_error_envio_cuenta

ASUNTO_ACUSE = "TICKET recibido"

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


def enviar_notificacion_ticket(destinatario, asunto, cuerpo, headers=None):
    """Envía la notificación del ticket. Devuelve (exito, mensaje)."""
    cuenta = EmpresaConfig.get_config().cuenta_soporte()
    if not cuenta.configurada:
        return False, SIN_CUENTA

    email = EmailMessage(
        subject=asunto,
        body=cuerpo,
        from_email=cuenta.from_header(),
        to=[destinatario],
        headers=headers or {},
        connection=conexion_smtp_cuenta(cuenta),
    )
    try:
        email.send(fail_silently=False)
        return True, f"Notificación enviada a {destinatario}."
    except Exception as exc:
        return False, mensaje_error_envio_cuenta(exc, cuenta)


def cuerpo_acuse(ticket):
    """Respuesta automática a un ticket abierto desde un correo entrante."""
    saludo = f"Hola {ticket.contacto_nombre}," if ticket.contacto_nombre else "Hola,"
    recibido = timezone.localtime(ticket.email_fecha or ticket.fecha_inicio).strftime('%d/%m/%Y a las %H:%M')
    return (
        f"{saludo}\n\n"
        f"Ticket recibido N° {ticket.numero}.\n\n"
        f"Registramos tu pedido de soporte:\n"
        f"  - Número de ticket: {ticket.numero}\n"
        f"  - Empresa: {ticket.cliente.nombre_completo}\n"
        f"  - Asunto: {ticket.titulo}\n"
        f"  - Recibido el {recibido} hs\n\n"
        f"Te mantendremos al tanto de su avance. Por favor, mencioná el número "
        f"{ticket.numero} en cualquier comunicación sobre este tema.\n\n"
        f"Saludos."
    )


def enviar_acuse_recibo(ticket):
    """Responde al remitente 'TICKET recibido' con el número del ticket.
    Si el envío sale bien, marca `acuse_enviado`. Devuelve (exito, mensaje)."""
    destinatario = ticket.contacto_email or ticket.email_remitente
    if not destinatario:
        return False, "El ticket no tiene email de contacto."

    headers = {'Auto-Submitted': 'auto-replied'}
    if ticket.email_message_id and not ticket.email_message_id.startswith('sin-id:'):
        # Para que el cliente lo vea en el mismo hilo que su pedido.
        headers['In-Reply-To'] = ticket.email_message_id
        headers['References'] = ticket.email_message_id

    exito, mensaje = enviar_notificacion_ticket(
        destinatario, ASUNTO_ACUSE, cuerpo_acuse(ticket), headers=headers,
    )
    if exito:
        ticket.acuse_enviado = timezone.now()
        ticket.save(update_fields=['acuse_enviado'])
    return exito, mensaje
