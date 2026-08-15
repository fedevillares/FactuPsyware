"""
launcher.py - Lanzador de escritorio para FactuPsyware.

Replica el comportamiento de iniciar_facturacion.bat / iniciar_facturacion_produccion.bat
pero como un .exe standalone (compilado con PyInstaller) para poder tener un icono
de escritorio en vez de un .bat.

Uso: FactuPsyware.exe -> levanta el servidor y abre el navegador.

La eleccion de autorizar una factura en PRUEBA (homologacion) o REAL
(produccion) ya no se fija al arrancar: se elige por factura, en la
propia pantalla de la factura al emitir (ver facturas/views.py:emitir).

IMPORTANTE sobre rutas: este script se ejecuta tanto como .py (dev) como
congelado dentro de un .exe con PyInstaller. En ambos casos BASE_DIR debe
apuntar a la carpeta del proyecto (donde estan manage.py, venv/, config/).
Nunca se pasa un archivo como cwd/argumento de directorio a subprocess:
siempre se resuelve con pathlib y se valida con .is_dir() / .exists()
antes de usarlo, para evitar el WinError 267 (NotADirectoryError) que
rompia la version anterior del launcher.
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if getattr(sys, "frozen", False):
    # Ejecutando como .exe: el proyecto vive en la misma carpeta que el .exe.
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

VENV_DIR = BASE_DIR / "venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
VENV_PYTHONW = VENV_DIR / "Scripts" / "pythonw.exe"
VENV_PIP_MARKER = VENV_DIR / ".deps_ok"
REQUIREMENTS = BASE_DIR / "config" / "requirements.txt"
MANAGE_PY = BASE_DIR / "manage.py"
LOGS_DIR = BASE_DIR / "logs"


def pausar_y_salir(codigo=1):
    input("\nPresione Enter para salir . . . ")
    sys.exit(codigo)


# Puerto fijo, distinto al de Django (8000), para el mini servidor que le
# informa a static/inicio.html en que paso va el arranque (venv, dependencias,
# migraciones, servidor) mientras Django todavia no esta levantado.
PUERTO_ESTADO = 8765
ESTADO_ACTUAL = {"mensaje": "Iniciando…"}


class _EstadoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/estado":
            self.send_response(404)
            self.end_headers()
            return
        cuerpo = json.dumps(ESTADO_ACTUAL).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, format, *args):
        pass  # no ensuciar la consola con el log de cada request de polling


def iniciar_servidor_estado():
    """Levanta en un hilo aparte un mini servidor HTTP local que expone el
    paso actual del arranque, para que static/inicio.html lo muestre en la
    web en vez de que el usuario tenga que mirar la consola."""
    try:
        servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO_ESTADO), _EstadoHandler)
    except OSError:
        return None  # puerto ocupado: la pantalla de inicio seguira mostrando su mensaje por defecto
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    return servidor


def set_estado(mensaje):
    ESTADO_ACTUAL["mensaje"] = mensaje
    print(mensaje)


def encontrar_python_sistema():
    """Busca un Python instalado en el sistema (py launcher o python en PATH)."""
    for candidato in ("py", "python"):
        try:
            r = subprocess.run(
                [candidato, "--version"],
                cwd=str(BASE_DIR),
                capture_output=True,
                timeout=10,
            )
            if r.returncode == 0:
                return candidato
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def matar_procesos_colgados():
    for nombre in ("pythonw.exe", "python.exe"):
        subprocess.run(
            ["taskkill", "/f", "/im", nombre],
            capture_output=True,
        )


def venv_funciona():
    if not VENV_PYTHON.is_file():
        return False
    if not (VENV_DIR / "Scripts" / "pip.exe").is_file():
        return False
    try:
        r = subprocess.run(
            [str(VENV_PYTHON), "-c", "import django"],
            cwd=str(BASE_DIR),
            capture_output=True,
            timeout=15,
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def recrear_venv(py_launcher):
    set_estado("Preparando el entorno por primera vez… puede tardar uno o dos minutos.")
    time.sleep(1)

    if VENV_DIR.exists():
        import shutil

        try:
            shutil.rmtree(VENV_DIR)
        except OSError:
            pass

    if VENV_DIR.exists():
        print()
        print("=" * 60)
        print('ERROR: no se pudo borrar la carpeta "venv" (acceso denegado).')
        print("Cerra cualquier ventana de Facturacion o Python abierta")
        print("y volve a intentar.")
        print("=" * 60)
        pausar_y_salir(1)

    r = subprocess.run([py_launcher, "-m", "venv", str(VENV_DIR)], cwd=str(BASE_DIR))
    if r.returncode != 0 or not VENV_PYTHON.is_file():
        print("ERROR: no se pudo crear el entorno virtual. Revisa que Python este bien instalado.")
        pausar_y_salir(1)

    if VENV_PIP_MARKER.exists():
        VENV_PIP_MARKER.unlink()


def instalar_dependencias_si_hace_falta():
    need_install = False
    if not VENV_PIP_MARKER.exists():
        need_install = True
    else:
        actual = REQUIREMENTS.read_bytes()
        marcado = VENV_PIP_MARKER.read_bytes()
        if actual != marcado:
            need_install = True

    if not need_install:
        return

    set_estado("Instalando dependencias necesarias…")
    subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip", "-q"], cwd=str(BASE_DIR))
    r = subprocess.run(
        [str(VENV_PYTHON), "-m", "pip", "install", "-r", str(REQUIREMENTS), "-q"],
        cwd=str(BASE_DIR),
    )
    if r.returncode != 0:
        print()
        print("ERROR: fallo la instalacion de dependencias. Revisa tu conexion a internet.")
        pausar_y_salir(1)

    VENV_PIP_MARKER.write_bytes(REQUIREMENTS.read_bytes())
    set_estado("Dependencias instaladas correctamente.")


def aplicar_migraciones_si_hace_falta():
    r = subprocess.run(
        [str(VENV_PYTHON), "manage.py", "migrate", "--check"],
        cwd=str(BASE_DIR),
        capture_output=True,
    )
    if r.returncode != 0:
        set_estado("Actualizando la base de datos…")
        subprocess.run([str(VENV_PYTHON), "manage.py", "migrate"], cwd=str(BASE_DIR))


def asegurar_permisos_restringidos(ruta):
    """Restringe una carpeta o archivo sensible (claves privadas de AFIP,
    SECRET_KEY, db.sqlite3) a solo el usuario actual, usando ACLs reales de
    Windows -- os.chmod no tiene efecto en NTFS. No es fatal si falla (por
    ejemplo, en una unidad de red que no soporte ACLs)."""
    if not ruta.exists():
        return
    usuario = os.environ.get("USERNAME", "")
    if not usuario:
        return
    if ruta.is_dir():
        args = ["icacls", str(ruta), "/inheritance:r", "/grant:r", f"{usuario}:(OI)(CI)F", "/T"]
    else:
        args = ["icacls", str(ruta), "/inheritance:r", "/grant:r", f"{usuario}:F"]
    subprocess.run(args, capture_output=True)


def advertir_si_carpeta_sincronizada():
    """Las claves privadas de AFIP no deberian vivir en una carpeta que se
    sincroniza a la nube (OneDrive, Google Drive, Dropbox): un backup en la
    nube comprometido filtra la clave de produccion. Solo advierte, no
    bloquea el arranque."""
    ruta_str = str(BASE_DIR).lower()
    marcadores = ("onedrive", "google drive", "dropbox", "icloud")
    if any(m in ruta_str for m in marcadores):
        print()
        print("=" * 60)
        print("ADVERTENCIA: la carpeta del proyecto parece estar dentro de")
        print("una carpeta sincronizada a la nube (OneDrive/Drive/Dropbox).")
        print("Las claves privadas de AFIP en certificados/ se subirian a")
        print("la nube junto con el resto de la carpeta. Se recomienda mover")
        print("el proyecto fuera de esa carpeta.")
        print("=" * 60)
        print()


def levantar_servidor():
    set_estado("Iniciando el servidor…")
    LOGS_DIR.mkdir(exist_ok=True)

    log_path = LOGS_DIR / "server.log"
    with open(log_path, "wb") as log:
        # 127.0.0.1: solo acepta conexiones desde esta misma PC. Antes era
        # 0.0.0.0 (LAN completa) para poder abrir la app desde el celular,
        # pero sin HTTPS por delante el login y la cookie de sesion viajaban
        # sin cifrar por la WiFi -- revisado 2026-08-15, ver security-review.md
        # hallazgo A1. Si hace falta volver a abrir el acceso desde otros
        # dispositivos, hay que ponerle TLS delante primero.
        subprocess.Popen(
            [str(VENV_PYTHONW), "manage.py", "runserver", "127.0.0.1:8000"],
            cwd=str(BASE_DIR),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )

    set_estado("Conectando con el servidor…")
    intentos = 0
    while intentos < 40:
        try:
            resp = urllib.request.urlopen("http://127.0.0.1:8000/", timeout=1)
            if resp.status < 500:
                break
        except Exception:
            pass
        intentos += 1
        time.sleep(1)

    set_estado("Listo. Esta ventana se puede cerrar.")
    # Antes había un time.sleep(3) decorativo acá: la pantalla de inicio ya
    # se redirige sola por polling (abrir_pantalla_inicio), así que no hacía
    # falta retener el arranque 3 segundos más.


def abrir_pantalla_inicio():
    """Abre la pantalla de carga (static/inicio.html) apenas arranca el
    .exe, para que el usuario vea algo enseguida en vez de una consola en
    blanco mientras se prepara el entorno (venv, dependencias, migraciones).
    La propia pagina hace polling al servidor y se redirige sola en cuanto
    Django responde, asi que no hace falta abrir el navegador de nuevo
    despues."""
    pantalla = BASE_DIR / "static" / "inicio.html"
    if pantalla.is_file():
        webbrowser.open(pantalla.resolve().as_uri())


def main():
    if not MANAGE_PY.is_file():
        print()
        print("=" * 60)
        print("ERROR: no se encontro manage.py junto al ejecutable.")
        print(f"Se esperaba en: {MANAGE_PY}")
        print("Este .exe debe estar en la raiz del proyecto FactuPsyware.")
        print("=" * 60)
        pausar_y_salir(1)

    advertir_si_carpeta_sincronizada()

    iniciar_servidor_estado()
    abrir_pantalla_inicio()
    matar_procesos_colgados()

    if not venv_funciona():
        # encontrar_python_sistema() solo hace falta para reconstruir el venv:
        # se busca acá adentro, no antes, para no pagar ese subprocess (~200-400ms)
        # en el 99% de los arranques donde el venv ya esta bien.
        py_launcher = encontrar_python_sistema()
        if py_launcher is None:
            print()
            print("=" * 60)
            print("ERROR: No se encontro Python instalado en esta computadora.")
            print("Instalalo desde https://www.python.org/downloads/")
            print('(marcar la casilla "Add Python to PATH" durante la instalacion)')
            print("y volve a ejecutar este archivo.")
            print("=" * 60)
            print()
            pausar_y_salir(1)
        recrear_venv(py_launcher)

    instalar_dependencias_si_hace_falta()
    aplicar_migraciones_si_hace_falta()
    asegurar_permisos_restringidos(BASE_DIR / "certificados")
    asegurar_permisos_restringidos(BASE_DIR / "secret_key.txt")
    asegurar_permisos_restringidos(BASE_DIR / "db.sqlite3")
    levantar_servidor()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print()
        print("=" * 60)
        print(f"ERROR inesperado: {exc}")
        print("=" * 60)
        pausar_y_salir(1)
