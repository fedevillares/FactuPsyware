"""Cifrado simetrico para secretos guardados en la base (ej. la contraseña
SMTP de EmpresaConfig), que de otro modo quedarian en texto plano en
db.sqlite3 y en cualquier backup exportado. La clave se deriva de
SECRET_KEY: no hace falta gestionar una clave aparte, pero rotar
SECRET_KEY invalida los valores ya cifrados (aceptable: se vuelven a
tipear en el admin)."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    clave = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(clave))


def cifrar(texto_plano):
    """Cifra un string para guardarlo en la base. Devuelve '' si texto_plano
    es vacio/None (nunca lanza)."""
    if not texto_plano:
        return ''
    return _fernet().encrypt(texto_plano.encode('utf-8')).decode('utf-8')


def descifrar(texto_cifrado):
    """Descifra un valor guardado con cifrar(). Devuelve '' si esta vacio o
    si no es un token valido (dato viejo sin cifrar, SECRET_KEY rotada,
    corrupcion) -- nunca lanza."""
    if not texto_cifrado:
        return ''
    try:
        return _fernet().decrypt(texto_cifrado.encode('utf-8')).decode('utf-8')
    except (InvalidToken, ValueError):
        return ''
