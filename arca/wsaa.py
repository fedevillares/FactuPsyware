import os
import json
import base64
import datetime
from lxml import etree
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7, Encoding
from cryptography.hazmat.primitives.serialization.pkcs7 import PKCS7Options
from cryptography import x509

from . import config


TA_CACHE_PATH = os.path.join(
    config.BASE_DIR, 'certificados', f'ta_cache_{config.ENTORNO}.json'
)


def generar_tra():
    """Genera el XML del Ticket de Requerimiento de Acceso (TRA)."""
    ahora = datetime.datetime.now()
    desde = ahora - datetime.timedelta(minutes=10)
    hasta = ahora + datetime.timedelta(minutes=10)

    unique_id = int(ahora.timestamp())

    tra = f"""<?xml version="1.0" encoding="UTF-8"?>
<loginTicketRequest version="1.0">
    <header>
        <uniqueId>{unique_id}</uniqueId>
        <generationTime>{desde.strftime('%Y-%m-%dT%H:%M:%S')}</generationTime>
        <expirationTime>{hasta.strftime('%Y-%m-%dT%H:%M:%S')}</expirationTime>
    </header>
    <service>{config.SERVICE}</service>
</loginTicketRequest>"""

    return tra


def firmar_tra(tra_xml, cert_path=None, key_path=None):
    """Firma el TRA con el certificado y clave privada, devuelve el CMS en base64.
    Si no se pasan cert_path/key_path, usa los del entorno activo (config)."""
    cert_path = cert_path or config.CERT_PATH
    key_path = key_path or config.KEY_PATH

    with open(key_path, 'rb') as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    with open(cert_path, 'rb') as f:
        certificate = x509.load_pem_x509_certificate(f.read())

    cms = pkcs7.PKCS7SignatureBuilder().set_data(
        tra_xml.encode('utf-8')
    ).add_signer(
        certificate, private_key, hashes.SHA256()
    ).sign(
        Encoding.DER, [PKCS7Options.Binary]
    )

    return base64.b64encode(cms).decode('utf-8')


def autenticar(datos=None):
    """Realiza el login contra WSAA, reutilizando el TA cacheado si sigue vigente.

    Si se pasa `datos` (dict con cert_path/key_path/wsaa_url/ta_cache_path,
    ver arca.config.datos_entorno), autentica contra ese entorno puntual.
    Si no, usa el entorno activo del proceso (config.ENTORNO)."""
    if datos is None:
        cert_path = config.CERT_PATH
        key_path = config.KEY_PATH
        wsaa_url = config.WSAA_URL
        ta_cache_path = TA_CACHE_PATH
    else:
        cert_path = datos['cert_path']
        key_path = datos['key_path']
        wsaa_url = datos['wsaa_url']
        ta_cache_path = datos['ta_cache_path']

    # Intentar usar el TA cacheado
    if os.path.exists(ta_cache_path):
        with open(ta_cache_path, 'r') as f:
            cache = json.load(f)
        expiracion = datetime.datetime.fromisoformat(cache['expiration'])
        if expiracion.tzinfo is not None:
            expiracion = expiracion.replace(tzinfo=None)
        if expiracion > datetime.datetime.now():
            return cache['token'], cache['sign']

    # Generar uno nuevo
    tra = generar_tra()
    cms = firmar_tra(tra, cert_path=cert_path, key_path=key_path)

    client = config.get_zeep_client(wsaa_url)
    response = client.service.loginCms(cms)

    root = etree.fromstring(response.encode('utf-8'))

    token = root.findtext('.//token')
    sign = root.findtext('.//sign')
    expiration_str = root.findtext('.//expirationTime')

    # Guardar en caché
    with open(ta_cache_path, 'w') as f:
        json.dump({
            'token': token,
            'sign': sign,
            'expiration': expiration_str,
        }, f)

    return token, sign
