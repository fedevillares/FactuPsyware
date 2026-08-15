import os
import ssl
import requests
import zeep
from zeep.transports import Transport
from requests.adapters import HTTPAdapter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CUIT = '20266034521'  # CUIT de la empresa

SERVICE = 'wsfe'


def datos_entorno(entorno):
    """Devuelve los datos de configuración (certificado, clave, URLs) para
    el entorno indicado ('homologacion' o 'produccion'), sin depender de
    variables de entorno globales. Permite inspeccionar ambos entornos
    a la vez (por ejemplo, en el panel de verificación)."""
    if entorno == 'produccion':
        return {
            'entorno': 'produccion',
            'cert_path': os.path.join(BASE_DIR, 'certificados', 'FACTUPSYWARE_prod.crt'),
            'key_path': os.path.join(BASE_DIR, 'certificados', 'psywareprod.key'),
            'wsaa_url': 'https://wsaa.afip.gov.ar/ws/services/LoginCms',
            'wsfe_url': 'https://servicios1.afip.gov.ar/wsfev1/service.asmx',
            'ta_cache_path': os.path.join(BASE_DIR, 'certificados', 'ta_cache_produccion.json'),
        }
    return {
        'entorno': 'homologacion',
        'cert_path': os.path.join(BASE_DIR, 'certificados', 'certificado.crt'),
        'key_path': os.path.join(BASE_DIR, 'certificados', 'privada.key'),
        'wsaa_url': 'https://wsaahomo.afip.gov.ar/ws/services/LoginCms',
        'wsfe_url': 'https://wswhomo.afip.gov.ar/wsfev1/service.asmx',
        'ta_cache_path': os.path.join(BASE_DIR, 'certificados', 'ta_cache_homologacion.json'),
    }


# El entorno ('homologacion' o 'produccion') ya no es fijo para todo el
# proceso: se elige por factura al emitir (ver facturas/views.py:emitir y
# arca/services.py:emitir_factura). Usar siempre datos_entorno(entorno)
# para obtener cert/clave/URLs de un entorno puntual.


class _AfipSSLAdapter(HTTPAdapter):
    """Adaptador HTTPS que permite cifrados/DH viejos, requeridos por los
    servidores de AFIP (rechazados por defecto en OpenSSL 3.x con el error
    'DH_KEY_TOO_SMALL'). Solo se usa para conectar a AFIP, no afecta al
    resto del sistema.

    NOTA DE SEGURIDAD (revisado 2026-08-15): esto baja el nivel de
    ciphers/DH aceptados (SECLEVEL=1), pero la verificacion de certificado
    del servidor de AFIP sigue activa (ssl.create_default_context(), sin
    check_hostname=False ni verify=False en ningun lado). Es un downgrade
    acotado y necesario para interoperar con los servidores de AFIP, no un
    descuido -- revisar si AFIP actualiza su infraestructura TLS."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        kwargs['ssl_context'] = ctx
        return super().proxy_manager_for(*args, **kwargs)


def get_zeep_client(wsdl_url):
    """Crea un zeep.Client apuntando a wsdl_url, usando una sesión HTTP que
    tolera las claves DH chicas de los servidores de AFIP. Usar esta función
    en vez de zeep.Client(wsdl=...) directo en todo el código que hable con
    AFIP (wsaa.py, wsfe.py, diagnostico.py)."""
    session = requests.Session()
    session.mount('https://', _AfipSSLAdapter())
    # Timeout explícito: sin esto, una conexión colgada a AFIP bloquea el
    # request indefinidamente (causa típica de "se cuelga", ver
    # "0 - Si algo se cuelga, ejecutar esto.bat").
    transport = Transport(session=session, timeout=20, operation_timeout=30)
    return zeep.Client(wsdl=wsdl_url + '?WSDL', transport=transport)
