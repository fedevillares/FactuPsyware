import os
import shutil
import datetime

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse, Http404
from django.conf import settings
from django.contrib import messages

from .diagnostico import verificar_todos
from .models import EmpresaConfig


@login_required
def panel_verificacion(request):
    resultados = verificar_todos()
    return render(request, 'arca/verificacion.html', {
        'homologacion': resultados['homologacion'],
        'produccion': resultados['produccion'],
        'email_configurado': bool(EmpresaConfig.get_config().email_remitente),
    })


@login_required
@require_POST
def probar_email(request):
    from facturas.emailing import enviar_email_prueba

    resultados = verificar_todos()
    destinatario = request.POST.get('destinatario_prueba', '').strip()

    if not destinatario:
        email_mensaje, email_exito = 'Ingresá un email de destino.', False
    else:
        email_exito, email_mensaje = enviar_email_prueba(destinatario)

    return render(request, 'arca/verificacion.html', {
        'homologacion': resultados['homologacion'],
        'produccion': resultados['produccion'],
        'email_configurado': bool(EmpresaConfig.get_config().email_remitente),
        'email_mensaje': email_mensaje,
        'email_exito': email_exito,
        'destinatario_prueba': destinatario,
    })


# ──────────────────────────────────────────────
# Backup y restauración de base de datos
# ──────────────────────────────────────────────

DB_PATH = settings.BASE_DIR / 'db.sqlite3'
BACKUP_DIR = settings.BASE_DIR / 'backups'


def _listar_backups():
    """Devuelve lista de dicts con info de cada backup, ordenada del más nuevo al más viejo."""
    if not BACKUP_DIR.exists():
        return []
    archivos = sorted(BACKUP_DIR.glob('backup_*.sqlite3'), reverse=True)
    result = []
    for f in archivos:
        stat = f.stat()
        result.append({
            'nombre': f.name,
            'fecha': datetime.datetime.fromtimestamp(stat.st_mtime),
            'size_kb': round(stat.st_size / 1024, 1),
        })
    return result


def _verificar_password(request):
    """Exige que el usuario re-tipee su contraseña de login antes de una
    accion de alto impacto (exportar/restaurar toda la base). Una sesion
    robada no alcanza sola para exfiltrar o reemplazar los datos."""
    clave = request.POST.get('clave_confirmacion', '')
    if not clave or not request.user.check_password(clave):
        messages.error(request, 'Contraseña incorrecta. Volvé a intentarlo.')
        return False
    return True


@login_required
def panel_backup(request):
    backups = _listar_backups()
    return render(request, 'arca/backup.html', {'backups': backups})


@login_required
@require_POST
def exportar_db(request):
    """Descarga la DB actual como archivo sqlite3."""
    if not _verificar_password(request):
        return redirect('panel_backup')

    if not DB_PATH.exists():
        messages.error(request, 'No se encontró la base de datos.')
        return redirect('panel_backup')

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    nombre = f'FactuPsyware_backup_{timestamp}.sqlite3'

    with open(DB_PATH, 'rb') as f:
        data = f.read()

    resp = HttpResponse(data, content_type='application/x-sqlite3')
    resp['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return resp


@login_required
@require_POST
def guardar_backup_local(request):
    """Guarda una copia de la DB en la carpeta backups/ del proyecto."""
    if not _verificar_password(request):
        return redirect('panel_backup')

    if not DB_PATH.exists():
        messages.error(request, 'No se encontró la base de datos.')
        return redirect('panel_backup')

    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = BACKUP_DIR / f'backup_{timestamp}.sqlite3'
    shutil.copy2(DB_PATH, dest)

    messages.success(request, f'Backup guardado: {dest.name}')
    return redirect('panel_backup')


@login_required
@require_POST
def importar_db(request):
    """Restaura la DB desde un archivo subido por el usuario."""
    if not _verificar_password(request):
        return redirect('panel_backup')

    archivo = request.FILES.get('archivo_db')
    if not archivo:
        messages.error(request, 'No seleccionaste ningún archivo.')
        return redirect('panel_backup')

    # Confirmación explícita del servidor: el diálogo JS de confirm() se
    # puede saltear (JS deshabilitado, request directo), así que se exige
    # además que el usuario tipee la frase de confirmación en el POST.
    if request.POST.get('confirmacion', '').strip().upper() != 'RESTAURAR':
        messages.error(request, 'Debés escribir RESTAURAR para confirmar el reemplazo de la base de datos.')
        return redirect('panel_backup')

    # Validaciones básicas
    if not archivo.name.endswith('.sqlite3'):
        messages.error(request, 'El archivo debe ser .sqlite3')
        return redirect('panel_backup')

    if archivo.size > 200 * 1024 * 1024:  # 200 MB máximo
        messages.error(request, 'El archivo es demasiado grande (máx. 200 MB).')
        return redirect('panel_backup')

    # Verificar que es SQLite válido (magic bytes)
    header = archivo.read(16)
    archivo.seek(0)
    if not header.startswith(b'SQLite format 3'):
        messages.error(request, 'El archivo no es una base de datos SQLite válida.')
        return redirect('panel_backup')

    # Guardar backup de la DB actual antes de reemplazar
    BACKUP_DIR.mkdir(exist_ok=True)
    if DB_PATH.exists():
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        shutil.copy2(DB_PATH, BACKUP_DIR / f'backup_preimport_{timestamp}.sqlite3')

    # Escribir la nueva DB
    with open(DB_PATH, 'wb') as f:
        for chunk in archivo.chunks():
            f.write(chunk)

    messages.success(
        request,
        'Base de datos restaurada correctamente. '
        'Se guardó un backup automático de la anterior. '
        'Reiniciá el servidor para que los cambios tengan efecto.'
    )
    return redirect('panel_backup')


@login_required
@require_POST
def eliminar_backup(request):
    """Elimina un backup local por nombre."""
    nombre = request.POST.get('nombre', '').strip()
    # Seguridad: solo permitir nombres de backup válidos, sin path traversal
    if not nombre or not nombre.startswith('backup_') or not nombre.endswith('.sqlite3'):
        messages.error(request, 'Nombre de backup inválido.')
        return redirect('panel_backup')

    ruta = BACKUP_DIR / nombre
    # Verificar que el archivo resuelve dentro de BACKUP_DIR
    try:
        ruta.resolve().relative_to(BACKUP_DIR.resolve())
    except ValueError:
        messages.error(request, 'Ruta inválida.')
        return redirect('panel_backup')

    if not ruta.exists():
        messages.error(request, 'El backup no existe.')
        return redirect('panel_backup')

    ruta.unlink()
    messages.success(request, f'Backup {nombre} eliminado.')
    return redirect('panel_backup')


@login_required
@require_POST
def descargar_backup_local(request):
    """Descarga un backup guardado localmente."""
    if not _verificar_password(request):
        return redirect('panel_backup')

    nombre = request.POST.get('nombre', '').strip()
    if not nombre or not nombre.startswith('backup_') or not nombre.endswith('.sqlite3'):
        raise Http404

    ruta = BACKUP_DIR / nombre
    try:
        ruta.resolve().relative_to(BACKUP_DIR.resolve())
    except ValueError:
        raise Http404

    if not ruta.exists():
        raise Http404

    with open(ruta, 'rb') as f:
        data = f.read()

    resp = HttpResponse(data, content_type='application/x-sqlite3')
    resp['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return resp
