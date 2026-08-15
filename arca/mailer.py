"""Plumbing SMTP compartido.

Centraliza la conexión SMTP y los mensajes de error para que tanto el envío de
facturas (`facturas/emailing.py`) como la ticketera (`tickets/emailing.py`) usen
la misma cuenta configurada en `EmpresaConfig`, sin duplicar código.
"""
import socket

from django.core.mail import get_connection

from .models import EmpresaConfig

TIMEOUT_SMTP_SEGUNDOS = 15


def empresa_tiene_email_configurado(empresa=None):
    empresa = empresa or EmpresaConfig.get_config()
    return bool(empresa.email_remitente and empresa.email_password)


def conexion_smtp(empresa):
    return get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=empresa.email_host,
        port=empresa.email_port,
        username=empresa.email_remitente,
        password=empresa.email_password_plano,
        use_tls=empresa.email_use_tls,
        timeout=TIMEOUT_SMTP_SEGUNDOS,
    )


def mensaje_error_envio(exc, empresa):
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return (
            f"El servidor {empresa.email_host}:{empresa.email_port} no respondió en "
            f"{TIMEOUT_SMTP_SEGUNDOS} segundos. Revisá el servidor/puerto SMTP y tu conexión a internet."
        )
    return f"No se pudo enviar el email: {exc}"
