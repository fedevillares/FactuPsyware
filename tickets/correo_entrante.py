"""Apertura automática de tickets desde correos entrantes.

Revisa por IMAP la bandeja de entrada de la cuenta de soporte
(`EmpresaConfig.cuenta_soporte()`). Por cada correo NO LEÍDO cuyo asunto
contenga "TICKET DE SOPORTE":

1. Se verifica que el remitente sea el "Email de soporte" de algún cliente
   (`Cliente.contacto_soporte_email`). Si no lo es, el correo se deja intacto
   (sigue sin leer en la bandeja) y no se abre nada.
2. Se abre un Ticket con título = asunto del correo, descripción = cuerpo del
   correo, y la fecha/hora del correo (encabezado Date).
3. Se marca el correo como leído y se responde al remitente con asunto
   "TICKET recibido" y el número del ticket.

Idempotencia: el Message-ID del correo se guarda en el ticket (único), así
que procesar dos veces el mismo correo no duplica tickets.

Lo usan: el hilo en segundo plano (`iniciar_revision_periodica`, arrancado
desde `TicketsConfig.ready()`), el botón "Revisar correo ahora" del listado
y el comando `manage.py revisar_correo_soporte`.
"""
import email
import hashlib
import imaplib
import logging
import os
import re
import ssl
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import timedelta
from email import policy
from email.utils import getaddresses, parsedate_to_datetime

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger('tickets.correo')

ASUNTO_CLAVE = "TICKET DE SOPORTE"
INTERVALO_SEGUNDOS = 60
TIMEOUT_IMAP_SEGUNDOS = 30
MAX_DESCRIPCION = 20000

# Un solo procesamiento a la vez (hilo periódico vs. botón manual).
_lock = threading.Lock()
# Correos ya descartados (remitente desconocido) para no loguearlos cada minuto.
_descartados_logueados = set()


@dataclass
class Resultado:
    creados: list = field(default_factory=list)      # tickets abiertos
    ignorados: int = 0                               # remitente no registrado / rechazado
    duplicados: int = 0                              # ya procesados antes
    acuses_fallidos: int = 0
    error: str = ''

    def resumen(self):
        if self.error:
            return self.error
        partes = [f"{len(self.creados)} ticket(s) nuevo(s)"]
        if self.ignorados:
            partes.append(f"{self.ignorados} correo(s) de remitentes no registrados como soporte de ningún cliente")
        if self.acuses_fallidos:
            partes.append(f"{self.acuses_fallidos} acuse(s) 'TICKET recibido' no se pudieron enviar (se reintenta solo)")
        return "Correo revisado: " + "; ".join(partes) + "."


# ── Parseo del correo ──────────────────────────────────────────────────────

def asunto_es_de_soporte(asunto):
    return ASUNTO_CLAVE in " ".join((asunto or "").upper().split())


def _remitente(msg):
    direcciones = getaddresses([str(msg.get('From', ''))])
    for nombre, direccion in direcciones:
        if direccion and '@' in direccion:
            return nombre.strip(), direccion.strip().lower()
    return '', ''


def _fecha(msg):
    try:
        fecha = parsedate_to_datetime(str(msg.get('Date', '')))
    except (TypeError, ValueError, IndexError):
        fecha = None
    if fecha is None:
        return timezone.now()
    if timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha, timezone.get_default_timezone())
    # Si el reloj del remitente está muy desfasado, se usa la hora de recepción.
    ahora = timezone.now()
    if fecha > ahora + timedelta(hours=1) or fecha < ahora - timedelta(days=30):
        return ahora
    return fecha


def _cuerpo(msg):
    """Texto del mensaje: prefiere text/plain; si solo hay HTML, lo pasa a texto."""
    parte = msg.get_body(preferencelist=('plain', 'html'))
    if parte is None:
        return ''
    try:
        texto = parte.get_content()
    except (LookupError, UnicodeDecodeError, AssertionError):
        payload = parte.get_payload(decode=True) or b''
        texto = payload.decode('utf-8', errors='replace')
    if parte.get_content_type() == 'text/html':
        texto = re.sub(r'(?is)<(script|style).*?</\1>', '', texto)
        texto = re.sub(r'(?i)<br\s*/?>|</p>|</div>', '\n', texto)
        texto = strip_tags(texto)
    texto = texto.replace('\r\n', '\n').replace('\r', '\n')
    texto = re.sub(r'\n{3,}', '\n\n', texto).strip()
    return texto[:MAX_DESCRIPCION]


def _message_id(msg, remitente, asunto):
    mid = str(msg.get('Message-ID', '') or '').strip()
    if mid:
        return mid[:500]
    base = f"{remitente}|{msg.get('Date', '')}|{asunto}".encode('utf-8', errors='replace')
    return 'sin-id:' + hashlib.sha256(base).hexdigest()


def _es_respuesta_automatica(msg):
    """Fuera de oficina, rebotes, etc.: no deben abrir tickets (evita bucles)."""
    auto = str(msg.get('Auto-Submitted', '') or '').strip().lower()
    if auto and auto != 'no':
        return True
    if str(msg.get('X-Autoreply', '') or msg.get('X-Autorespond', '')).strip():
        return True
    precedence = str(msg.get('Precedence', '') or '').strip().lower()
    return precedence in ('bulk', 'junk', 'auto_reply')


def _falla_autenticacion(msg):
    """True si el servidor receptor marcó el correo como suplantado
    (SPF/DKIM/DMARC 'fail'). Gmail y la mayoría de los proveedores agregan el
    encabezado Authentication-Results; si no está, no se puede afirmar nada y
    se acepta."""
    resultados = " ".join(str(v) for v in (msg.get_all('Authentication-Results') or [])).lower()
    return bool(re.search(r'\bdmarc=fail\b', resultados))


# ── Procesamiento ──────────────────────────────────────────────────────────

def procesar_mensaje(raw_bytes, cuenta_propia=''):
    """Procesa un correo crudo. Devuelve ('creado', ticket), ('duplicado', None)
    o ('ignorado', motivo). No envía el acuse: eso lo hace el llamador."""
    from clientes.models import Cliente
    from .models import Ticket

    msg = email.message_from_bytes(raw_bytes, policy=policy.default)
    asunto = " ".join(str(msg.get('Subject', '') or '').split())
    if not asunto_es_de_soporte(asunto):
        return 'ignorado', 'asunto distinto'

    nombre, remitente = _remitente(msg)
    if not remitente:
        return 'ignorado', 'sin remitente'
    if cuenta_propia and remitente == cuenta_propia.lower():
        return 'ignorado', 'enviado por la propia cuenta de soporte'
    if _es_respuesta_automatica(msg):
        return 'ignorado', 'respuesta automática'
    if _falla_autenticacion(msg):
        return 'ignorado', 'falló la verificación DMARC (posible suplantación)'

    cliente = (Cliente.objects.filter(contacto_soporte_email__iexact=remitente)
               .order_by('id').first())
    if cliente is None:
        return 'ignorado', f'{remitente} no es el email de soporte de ningún cliente'

    message_id = _message_id(msg, remitente, asunto)
    if Ticket.objects.filter(email_message_id=message_id).exists():
        return 'duplicado', None

    fecha = _fecha(msg)
    cuerpo = _cuerpo(msg) or '(El correo no tenía texto.)'
    try:
        with transaction.atomic():
            ticket = Ticket.objects.create(
                cliente=cliente,
                titulo=asunto[:200],
                descripcion=cuerpo,
                contacto_nombre=cliente.contacto_soporte_nombre or nombre,
                contacto_email=remitente,
                origen='EMAIL',
                email_message_id=message_id,
                email_remitente=remitente,
                email_fecha=fecha,
            )
            # fecha_inicio es auto_now_add: se ajusta a la hora del correo.
            Ticket.objects.filter(pk=ticket.pk).update(fecha_inicio=fecha)
            ticket.fecha_inicio = fecha
    except IntegrityError:
        return 'duplicado', None

    logger.info("Ticket %s abierto desde correo de %s (%s), Message-ID %s",
                ticket.numero, remitente, cliente.nombre_completo, message_id)
    return 'creado', ticket


def _reintentar_acuses_pendientes(resultado):
    from .models import Ticket
    from .emailing import enviar_acuse_recibo

    pendientes = Ticket.objects.select_related('cliente').filter(
        origen='EMAIL', acuse_enviado__isnull=True,
        creado__gte=timezone.now() - timedelta(days=2),
    )
    for ticket in pendientes:
        exito, mensaje = enviar_acuse_recibo(ticket)
        if exito:
            logger.info("Acuse 'TICKET recibido' de %s enviado a %s", ticket.numero, ticket.contacto_email)
        else:
            resultado.acuses_fallidos += 1
            logger.warning("No se pudo enviar el acuse de %s: %s", ticket.numero, mensaje)


def revisar_bandeja():
    """Revisa la bandeja una vez. Devuelve un `Resultado`. Nunca lanza."""
    from arca.models import EmpresaConfig

    resultado = Resultado()
    if not _lock.acquire(blocking=False):
        resultado.error = "Ya se está revisando el correo en este momento; probá de nuevo en unos segundos."
        return resultado
    try:
        cuenta = EmpresaConfig.get_config().cuenta_soporte()
        if not cuenta.configurada:
            resultado.error = ("No hay una cuenta de soporte configurada (email y contraseña) en "
                               "Configuración de la empresa.")
            return resultado
        if not cuenta.imap_host:
            resultado.error = "Falta el servidor IMAP en la configuración de la cuenta de soporte."
            return resultado

        try:
            _leer_imap(cuenta, resultado)
        except (imaplib.IMAP4.error, OSError, ssl.SSLError) as exc:
            resultado.error = (f"No se pudo leer la bandeja de {cuenta.usuario} "
                               f"({cuenta.imap_host}:{cuenta.imap_port}): {exc}")
            logger.warning(resultado.error)

        # Envía los acuses de los tickets recién creados y reintenta los que
        # hayan fallado en revisiones anteriores (ej. sin internet).
        _reintentar_acuses_pendientes(resultado)
        return resultado
    except Exception as exc:  # el hilo periódico no debe morir por nada
        logger.exception("Error inesperado revisando el correo de soporte")
        resultado.error = f"Error inesperado revisando el correo: {exc}"
        return resultado
    finally:
        _lock.release()


def _leer_imap(cuenta, resultado):
    contexto = ssl.create_default_context()
    imap = imaplib.IMAP4_SSL(cuenta.imap_host, cuenta.imap_port,
                             ssl_context=contexto, timeout=TIMEOUT_IMAP_SEGUNDOS)
    try:
        imap.login(cuenta.usuario, cuenta.password)
        typ, _ = imap.select('INBOX')
        if typ != 'OK':
            raise imaplib.IMAP4.error("no se pudo abrir la bandeja INBOX")
        typ, data = imap.uid('search', None, 'UNSEEN', 'SUBJECT', f'"{ASUNTO_CLAVE}"')
        if typ != 'OK':
            raise imaplib.IMAP4.error("la búsqueda de correos falló")
        uids = data[0].split() if data and data[0] else []

        for uid in uids:
            # BODY.PEEK: leer sin marcar como leído (se marca solo si se procesa).
            typ, partes = imap.uid('fetch', uid, '(BODY.PEEK[])')
            raw = next((p[1] for p in partes or [] if isinstance(p, tuple)), None)
            if typ != 'OK' or raw is None:
                continue

            estado, dato = procesar_mensaje(raw, cuenta_propia=cuenta.usuario)
            if estado == 'creado':
                resultado.creados.append(dato)
            elif estado == 'duplicado':
                resultado.duplicados += 1
            else:
                resultado.ignorados += 1
                clave = (cuenta.usuario, uid)
                if clave not in _descartados_logueados:
                    _descartados_logueados.add(clave)
                    logger.info("Correo UID %s no abrió ticket: %s", uid.decode(), dato)
                # Se deja sin leer: no es un pedido válido y el usuario debe verlo.
                continue

            imap.uid('store', uid, '+FLAGS', '(\\Seen)')
    finally:
        try:
            imap.logout()
        except Exception:
            pass


# ── Hilo en segundo plano ──────────────────────────────────────────────────

_hilo = None


def _bucle():
    from arca.models import EmpresaConfig
    from django.db import close_old_connections

    time.sleep(10)  # dejar que el servidor termine de arrancar
    while True:
        close_old_connections()
        try:
            if EmpresaConfig.get_config().soporte_recepcion_activa:
                resultado = revisar_bandeja()
                if resultado.creados:
                    logger.info(resultado.resumen())
        except Exception:
            logger.exception("Error en el ciclo de revisión del correo de soporte")
        finally:
            close_old_connections()
        time.sleep(INTERVALO_SEGUNDOS)


def debe_iniciar_hilo(argv=None, entorno=None):
    """Solo en el proceso que atiende requests de `runserver` (no en el
    proceso vigilante del autoreload, ni en migrate/test/shell)."""
    argv = sys.argv if argv is None else argv
    entorno = os.environ if entorno is None else entorno
    if entorno.get('FACTUPSYWARE_SIN_CORREO') == '1':
        return False
    if len(argv) < 2 or argv[1] != 'runserver':
        return False
    return '--noreload' in argv or entorno.get('RUN_MAIN') == 'true'


def iniciar_revision_periodica():
    global _hilo
    if _hilo is not None and _hilo.is_alive():
        return
    _hilo = threading.Thread(target=_bucle, name='correo-soporte', daemon=True)
    _hilo.start()
