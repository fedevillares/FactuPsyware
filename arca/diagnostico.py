"""
Panel de verificación de entornos ARCA/AFIP (homologación y producción).

Corre una serie de chequeos no destructivos para cada entorno:
  1. Certificado presente y legible.
  2. Clave privada presente y legible.
  3. El certificado y la clave corresponden entre sí (misma clave pública).
  4. Login WSAA exitoso (se firma un TRA real y se llama a loginCms).
  5. El servicio WSFE responde (FEDummy, no requiere autenticación).

No emite ningún comprobante ni modifica datos fiscales: todos los pasos
son de solo lectura / autenticación.
"""
import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography import x509

from . import config, wsaa


def _check_certificado(datos):
    cert_path = datos['cert_path']
    if not os.path.exists(cert_path):
        return {'ok': False, 'detalle': f"No se encontró el archivo: {cert_path}"}
    try:
        with open(cert_path, 'rb') as f:
            cert = x509.load_pem_x509_certificate(f.read())
        vencimiento = cert.not_valid_after_utc if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after
        emisor = cert.issuer.rfc4514_string()
        return {
            'ok': True,
            'detalle': f"OK. Emisor: {emisor}. Vence: {vencimiento.strftime('%d/%m/%Y')}",
            'cert': cert,
        }
    except Exception as e:
        return {'ok': False, 'detalle': f"Archivo presente pero ilegible/inválido: {e}"}


def _check_clave(datos):
    key_path = datos['key_path']
    if not os.path.exists(key_path):
        return {'ok': False, 'detalle': f"No se encontró el archivo: {key_path}"}
    try:
        with open(key_path, 'rb') as f:
            key = serialization.load_pem_private_key(f.read(), password=None)
        return {'ok': True, 'detalle': 'OK, clave privada legible.', 'key': key}
    except Exception as e:
        return {'ok': False, 'detalle': f"Archivo presente pero ilegible/inválido: {e}"}


def _check_correspondencia(cert, key):
    try:
        pub_cert = cert.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        pub_key = key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        if pub_cert == pub_key:
            return {'ok': True, 'detalle': 'El certificado y la clave privada corresponden entre sí.'}
        return {'ok': False, 'detalle': 'El certificado y la clave privada NO corresponden entre sí.'}
    except Exception as e:
        return {'ok': False, 'detalle': f"No se pudo comparar: {e}"}


def _check_login_wsaa(datos):
    try:
        token, sign = wsaa.autenticar(datos=datos)
        if token and sign:
            return {'ok': True, 'detalle': 'Login WSAA exitoso, token obtenido.'}
        return {'ok': False, 'detalle': 'WSAA respondió sin token/sign.'}
    except Exception as e:
        return {'ok': False, 'detalle': f"Error al autenticar contra WSAA: {e}"}


def _check_wsfe_alcanzable(datos):
    try:
        client = config.get_zeep_client(datos['wsfe_url'])
        response = client.service.FEDummy()
        return {
            'ok': True,
            'detalle': f"WSFE responde. AppServer={response.AppServer}, DbServer={response.DbServer}, AuthServer={response.AuthServer}",
        }
    except Exception as e:
        return {'ok': False, 'detalle': f"No se pudo contactar al WSFE: {e}"}


def verificar_entorno(entorno):
    """Corre todos los chequeos para 'homologacion' o 'produccion'.
    Devuelve un dict con cada chequeo y un booleano 'listo' global."""
    datos = config.datos_entorno(entorno)

    resultado = {
        'entorno': entorno,
        'certificado': _check_certificado(datos),
        'clave': _check_clave(datos),
    }

    if resultado['certificado']['ok'] and resultado['clave']['ok']:
        resultado['correspondencia'] = _check_correspondencia(
            resultado['certificado']['cert'], resultado['clave']['key']
        )
    else:
        resultado['correspondencia'] = {'ok': False, 'detalle': 'No se pudo verificar (falta certificado y/o clave).'}

    resultado['wsfe_alcanzable'] = _check_wsfe_alcanzable(datos)

    if resultado['certificado']['ok'] and resultado['clave']['ok'] and resultado['correspondencia']['ok']:
        resultado['login_wsaa'] = _check_login_wsaa(datos)
    else:
        resultado['login_wsaa'] = {'ok': False, 'detalle': 'No se intentó (faltan requisitos previos).'}

    # limpiar objetos no serializables antes de exponer
    resultado['certificado'] = {'ok': resultado['certificado']['ok'], 'detalle': resultado['certificado']['detalle']}
    resultado['clave'] = {'ok': resultado['clave']['ok'], 'detalle': resultado['clave']['detalle']}

    resultado['listo'] = all([
        resultado['certificado']['ok'],
        resultado['clave']['ok'],
        resultado['correspondencia']['ok'],
        resultado['wsfe_alcanzable']['ok'],
        resultado['login_wsaa']['ok'],
    ])

    return resultado


def verificar_todos():
    return {
        'homologacion': verificar_entorno('homologacion'),
        'produccion': verificar_entorno('produccion'),
    }
