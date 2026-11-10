"""
Cotización del dólar para facturar en moneda extranjera.

Interfaz:  get_rate(tipo=None, forzar=False) -> {'valor', 'fuente', 'fecha', ...}

  - Proveedor principal: DolarAPI. Respaldo automático: Bluelytics. Son APIs
    públicas, sin clave.
  - El tipo de cotización ('oficial', 'mayorista', 'blue', ...) y el campo
    ('venta' / 'compra') salen de settings (COTIZACION_DOLAR_TIPO /
    COTIZACION_DOLAR_CAMPO). Por defecto: oficial, venta.
  - Cache corto (COTIZACION_CACHE_SEGUNDOS) para no pegarle a la API en cada
    pantalla. Si los dos proveedores fallan se devuelve la última cotización
    buena que se haya obtenido (marcada 'desactualizada'); si tampoco hay,
    se lanza CotizacionNoDisponible y el formulario pide carga manual.

Sobre qué cotización corresponde: la RG 5616/2024 de ARCA indica el tipo de
cambio VENDEDOR DIVISA del Banco Nación al cierre del día hábil anterior a la
emisión. Estas APIs publican el oficial "billete" del momento, que es una
buena aproximación pero puede no coincidir al centavo con el que ARCA tiene
registrado (ver arca/wsfe.py:consultar_cotizacion para el valor de ARCA).
"""
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .moneda import redondear_cotizacion

# Hijo del logger 'arca': queda registrado en logs/arca_emisiones.log.
logger = logging.getLogger('arca.cotizacion')

# Cuánto se conserva la última cotización buena para usarla de respaldo si
# los proveedores están caídos.
SEGUNDOS_ULTIMA_BUENA = 24 * 60 * 60


class CotizacionNoDisponible(Exception):
    """Ningún proveedor respondió y no hay una cotización previa en cache."""


def _config(nombre, defecto):
    return getattr(settings, nombre, defecto)


def _a_cotizacion(valor):
    try:
        cotizacion = redondear_cotizacion(Decimal(str(valor)))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"cotización no numérica: {valor!r}")
    if cotizacion <= 0:
        raise ValueError(f"cotización no positiva: {valor!r}")
    return cotizacion


def _a_fecha(texto):
    fecha = parse_datetime(texto) if isinstance(texto, str) else None
    if fecha is None:
        return timezone.now()
    if timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha)
    return fecha


def _get_json(url):
    respuesta = requests.get(url, timeout=_config('COTIZACION_TIMEOUT_SEGUNDOS', 4))
    respuesta.raise_for_status()
    return respuesta.json()


def _dolarapi(tipo, campo):
    url = _config('COTIZACION_DOLARAPI_URL', 'https://dolarapi.com/v1/dolares/{tipo}')
    datos = _get_json(url.format(tipo=tipo))
    return _a_cotizacion(datos[campo]), _a_fecha(datos.get('fechaActualizacion'))


def _bluelytics(tipo, campo):
    # Bluelytics solo publica oficial y blue.
    if tipo not in ('oficial', 'blue'):
        raise ValueError(f"Bluelytics no publica el tipo '{tipo}'")
    datos = _get_json(_config('COTIZACION_BLUELYTICS_URL', 'https://api.bluelytics.com.ar/v2/latest'))
    clave = {'venta': 'value_sell', 'compra': 'value_buy'}[campo]
    return _a_cotizacion(datos[tipo][clave]), _a_fecha(datos.get('last_update'))


# En orden de preferencia: (nombre, función)
PROVEEDORES = [
    ('dolarapi', _dolarapi),
    ('bluelytics', _bluelytics),
]


def get_rate(tipo=None, forzar=False):
    """
    Devuelve la cotización del dólar (pesos por 1 USD):

        {'valor': Decimal, 'fuente': 'api:dolarapi', 'fecha': datetime (aware),
         'tipo': 'oficial', 'campo': 'venta', 'desactualizada': bool}

    `forzar=True` saltea el cache corto (botón "Actualizar cotización").
    Lanza CotizacionNoDisponible si no hay forma de obtener un valor.
    """
    tipo = tipo or _config('COTIZACION_DOLAR_TIPO', 'oficial')
    campo = _config('COTIZACION_DOLAR_CAMPO', 'venta')
    if campo not in ('venta', 'compra'):
        campo = 'venta'

    clave = f"cotizacion_dolar:{tipo}:{campo}"
    clave_ultima = f"{clave}:ultima_buena"

    if not forzar:
        en_cache = cache.get(clave)
        if en_cache:
            return en_cache

    for nombre, proveedor in PROVEEDORES:
        try:
            valor, fecha = proveedor(tipo, campo)
        except Exception as e:
            logger.warning("Cotización: falló el proveedor %s (tipo=%s): %s", nombre, tipo, e)
            continue
        resultado = {
            'valor': valor, 'fuente': f'api:{nombre}', 'fecha': fecha,
            'tipo': tipo, 'campo': campo, 'desactualizada': False,
        }
        cache.set(clave, resultado, _config('COTIZACION_CACHE_SEGUNDOS', 600))
        cache.set(clave_ultima, resultado, SEGUNDOS_ULTIMA_BUENA)
        logger.info("Cotización obtenida de %s: %s (tipo=%s %s)", nombre, valor, tipo, campo)
        return resultado

    ultima = cache.get(clave_ultima)
    if ultima:
        logger.warning("Cotización: sin proveedores disponibles, se usa la última obtenida (%s)", ultima['fecha'])
        return {**ultima, 'desactualizada': True}

    logger.error("Cotización: ningún proveedor disponible y sin valor previo en cache (tipo=%s)", tipo)
    raise CotizacionNoDisponible(
        "No se pudo obtener la cotización automática del dólar. Cargala manualmente."
    )


def desvio_porcentual(cotizacion, referencia):
    """Desvío absoluto (en %) de `cotizacion` respecto de `referencia`."""
    return abs(cotizacion - referencia) / referencia * Decimal('100')
