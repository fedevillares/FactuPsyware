"""
Django settings for facturacion project.
"""

import os
import stat
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)


def _get_secret_key():
    env_key = os.environ.get('DJANGO_SECRET_KEY')
    if env_key:
        return env_key
    key_file = BASE_DIR / 'secret_key.txt'
    if key_file.exists():
        return key_file.read_text(encoding='utf-8').strip()
    from django.core.management.utils import get_random_secret_key
    key = get_random_secret_key()
    key_file.write_text(key, encoding='utf-8')
    # Restringir permisos: solo lectura/escritura para el dueño del proceso
    try:
        key_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Windows puede no soportar todos los bits; no es fatal
    return key


SECRET_KEY = _get_secret_key()

DEBUG = os.environ.get('DJANGO_DEBUG', '0') == '1'


def _ips_lan_locales():
    """IPs de esta PC en la red local (WiFi/LAN), para poder abrir la app
    desde otros dispositivos conectados a la misma red. No sale a internet:
    solo consulta las interfaces de red del sistema operativo."""
    import socket
    ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:
        # Truco estándar para obtener la IP de salida real sin depender del
        # hostname (que en Windows a veces no resuelve bien): "conectar" un
        # socket UDP a una IP externa no envía ningún paquete, solo hace que
        # el sistema operativo elija la interfaz de salida correcta.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.8.8', 80))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return ips


_extra_hosts = os.environ.get('DJANGO_ALLOWED_HOSTS', '')
ALLOWED_HOSTS = (
    ['127.0.0.1', 'localhost']
    + list(_ips_lan_locales())
    + [h.strip() for h in _extra_hosts.split(',') if h.strip()]
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'clientes',
    'arca',
    'servicios',
    'facturas',
    'tickets',
    'crm',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'facturacion.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'arca.context_processors.empresa',
            ],
        },
    },
]

WSGI_APPLICATION = 'facturacion.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-ar'
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_THOUSAND_SEPARATOR = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/facturas/'

# Sesión: expira al cerrar el navegador; cookie solo por HTTP (no accesible desde JS)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Protección CSRF
CSRF_COOKIE_HTTPONLY = False  # Django necesita leerla desde JS para el token; False es el default correcto
CSRF_COOKIE_SAMESITE = 'Lax'

# Headers de seguridad: el navegador no debe abrir la app en un iframe de otro origen
X_FRAME_OPTIONS = 'SAMEORIGIN'

# Referrer policy: no filtrar la URL a recursos externos
SECURE_REFERRER_POLICY = 'same-origin'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'arca_file': {
            'class': 'logging.FileHandler',
            'filename': LOG_DIR / 'arca_emisiones.log',
            'formatter': 'verbose',
        },
        'django_file': {
            'class': 'logging.FileHandler',
            'filename': LOG_DIR / 'django_errors.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'arca': {
            'handlers': ['arca_file'],
            'level': 'INFO',
            'propagate': True,
        },
        'django': {
            'handlers': ['django_file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['django_file'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}
