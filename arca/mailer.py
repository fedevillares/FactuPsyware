"""Plumbing SMTP compartido.

Centraliza la conexión SMTP y los mensajes de error para que tanto el envío de
facturas (`facturas/emailing.py`) como la ticketera (`tickets/emailing.py`) usen
la misma cuenta configurada en `EmpresaConfig`, sin duplicar código.
"""
import socket
from dataclasses import dataclass

from django.core.mail import get_connection

from .models import EmpresaConfig

TIMEOUT_SMTP_SEGUNDOS = 15


def empresa_tiene_email_configurado(empresa=None):
    empresa = empresa or EmpresaConfig.get_config()
    return bool(empresa.email_remitente and empresa.email_password_plano)


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


@dataclass
class CuentaCorreo:
    """Datos de conexión de una cuenta de correo (SMTP para enviar, IMAP para
    recibir). La arma EmpresaConfig.cuenta_soporte() para la ticketera."""
    usuario: str
    password: str
    nombre: str
    smtp_host: str
    smtp_port: int
    smtp_tls: bool
    imap_host: str
    imap_port: int

    @property
    def configurada(self):
        return bool(self.usuario and self.password)

    def from_header(self):
        return f"{self.nombre} <{self.usuario}>" if self.nombre else self.usuario


def conexion_smtp_cuenta(cuenta):
    # Puerto 465 = SSL directo (típico de hostings cPanel); 587 = STARTTLS.
    # Django no permite ambos a la vez, así que el puerto decide.
    ssl_directo = cuenta.smtp_port == 465
    return get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=cuenta.smtp_host,
        port=cuenta.smtp_port,
        username=cuenta.usuario,
        password=cuenta.password,
        use_tls=cuenta.smtp_tls and not ssl_directo,
        use_ssl=ssl_directo,
        timeout=TIMEOUT_SMTP_SEGUNDOS,
    )


def mensaje_error_envio_cuenta(exc, cuenta):
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return (
            f"El servidor {cuenta.smtp_host}:{cuenta.smtp_port} no respondió en "
            f"{TIMEOUT_SMTP_SEGUNDOS} segundos. Revisá el servidor/puerto SMTP y tu conexión a internet."
        )
    return f"No se pudo enviar el email: {exc}"
