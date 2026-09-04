from django.core.mail import EmailMessage

from arca.models import EmpresaConfig
from arca.mailer import (
    empresa_tiene_email_configurado,
    conexion_smtp as _conexion_smtp,
    mensaje_error_envio as _mensaje_error_envio,
)
from arca.pdf_comprobante import generar_pdf
from arca.qr import generar_qr_base64


def _pdf_de_factura(factura, empresa):
    qr_b64 = generar_qr_base64(factura) if factura.cae else None
    otros_impuestos = round(float(factura.total) * float(empresa.otros_impuestos_pct) / 100, 2)
    return generar_pdf(
        factura=factura, empresa=empresa,
        otros_impuestos=otros_impuestos, qr_b64=qr_b64, es_preview=not factura.cae,
    )


def enviar_facturas_por_email(facturas, destinatario, asunto, cuerpo):
    """Envía una o varias facturas como adjuntos PDF en un único email.

    Devuelve (exito, mensaje).
    """
    empresa = EmpresaConfig.get_config()
    if not empresa_tiene_email_configurado(empresa):
        return False, "No hay una cuenta de email configurada. Configurala en el panel de administración (Configuración de la empresa)."

    connection = _conexion_smtp(empresa)

    email = EmailMessage(
        subject=asunto,
        body=cuerpo,
        from_email=empresa.email_from_header(),
        to=[destinatario],
        connection=connection,
    )

    for factura in facturas:
        pdf_bytes = _pdf_de_factura(factura, empresa)
        nombre = f"{factura.nombre_archivo}.pdf"
        email.attach(nombre, pdf_bytes, 'application/pdf')

    try:
        email.send(fail_silently=False)
        return True, f"Email enviado a {destinatario}."
    except Exception as exc:
        return False, _mensaje_error_envio(exc, empresa)


def enviar_email_prueba(destinatario):
    """Envía un email simple (sin adjuntos) para verificar que la configuración SMTP funciona.

    Devuelve (exito, mensaje).
    """
    empresa = EmpresaConfig.get_config()
    if not empresa_tiene_email_configurado(empresa):
        return False, "No hay una cuenta de email configurada. Configurala en el panel de administración (Configuración de la empresa)."

    connection = _conexion_smtp(empresa)

    email = EmailMessage(
        subject="Prueba de configuración — FactuPsyware",
        body=(
            f"Este es un email de prueba enviado desde FactuPsyware ({empresa.email_remitente}).\n\n"
            "Si lo estás leyendo, la configuración SMTP funciona correctamente."
        ),
        from_email=empresa.email_from_header(),
        to=[destinatario],
        connection=connection,
    )

    try:
        email.send(fail_silently=False)
        return True, f"Email de prueba enviado a {destinatario}."
    except Exception as exc:
        return False, _mensaje_error_envio(exc, empresa)
