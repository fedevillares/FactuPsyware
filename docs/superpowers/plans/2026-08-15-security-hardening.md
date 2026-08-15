# Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 3 High and 5 Medium findings from `.superpowers/sdd/security-review.md` that the project owner chose to act on now, per two explicit decisions made during scoping: (1) the server binds to `127.0.0.1` only (no LAN access — the owner confirmed they never use it from other devices), which makes M1 (swap `runserver` for a real WSGI server) unnecessary and **out of scope**; (2) M5 (AFIP TLS downgrade) needs only a documentation comment, already covered inside Task 5, not a standalone task.

**Architecture:** Each task is an independent, surgical fix to one specific finding — no shared new abstractions across tasks except `arca/crypto.py` (Task 3), which only Task 3 touches. Every task that changes a `models.py` file runs `makemigrations`/`migrate` as part of its steps. No task changes the public behavior of features unrelated to its finding.

**Tech Stack:** Django 6.0.6 (existing), `cryptography` (already a dependency, provides `Fernet` for Task 3), Pillow (already a dependency, provides image validation for Task 4). No new packages required for any task in this plan.

## Global Constraints

- Comments and user-facing text in Argentine Spanish (matches `.claude/CLAUDE.md`).
- Every model field that stores something derived stays a `@property`, never persisted (project convention).
- Run `"venv/Scripts/python.exe" manage.py check` after any task touching settings/models/urls.
- Run the full test suite (`"venv/Scripts/python.exe" manage.py test`) before committing each task — not just the new tests — since several tasks touch shared files (`arca/models.py`, `arca/views.py`).
- **Out of scope for this plan** (explicitly decided with the project owner): M1 (runserver → waitress/whitenoise) — do not touch `facturacion/urls.py`'s static-serving line, which `.claude/CLAUDE.md` marks "no tocar". Do not add new external dependencies.
- The project uses Windows with Git Bash. Use the venv's python directly for all commands: `"venv/Scripts/python.exe" manage.py test`, etc.

---

### Task 1: A1 — Restrict the server to localhost only

**Files:**
- Modify: `launcher.py`
- Modify: `.claude/CLAUDE.md`

**Interfaces:**
- Consumes: nothing new.
- Produces: the launched server now only accepts connections from the same PC. No other task depends on this one.

- [ ] **Step 1: Change the bind address in `launcher.py`**

In `launcher.py`, inside `levantar_servidor()`, find this block (around line 224-233):
```python
        # 0.0.0.0: acepta conexiones desde cualquier interfaz de red, no
        # solo desde esta PC, para poder abrir la app desde otros
        # dispositivos en la misma red local (celular, otra computadora).
        subprocess.Popen(
            [str(VENV_PYTHONW), "manage.py", "runserver", "0.0.0.0:8000"],
            cwd=str(BASE_DIR),
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
```

Replace it with:
```python
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
```

- [ ] **Step 2: Remove the now-misleading LAN-URL messaging**

Still in `levantar_servidor()`, find this block (around line 247-253):
```python
    ip = ip_lan()
    set_estado("Listo. Esta ventana se puede cerrar.")
    if ip:
        print()
        print(f"Para abrir la app desde otro dispositivo en la misma red (celular, otra PC):")
        print(f"  http://{ip}:8000/facturas/")
        print("(La primera vez, Windows puede pedir permiso de Firewall: aceptalo para redes privadas.)")
    time.sleep(3)
```

Replace it with:
```python
    set_estado("Listo. Esta ventana se puede cerrar.")
    time.sleep(3)
```

- [ ] **Step 3: Remove the now-unused `ip_lan()` function**

Find and delete this whole function (around line 206-215), since its only caller was removed in Step 2:
```python
def ip_lan():
    """IP de esta PC en la red local, para mostrarle al usuario cómo entrar
    desde el celular u otra PC conectados al mismo WiFi/router."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None
```

- [ ] **Step 4: Verify `launcher.py` still parses correctly**

Run: `"venv/Scripts/python.exe" -c "import ast; ast.parse(open('launcher.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

Also grep the file to confirm nothing else references `ip_lan`:
Run: `grep -n "ip_lan" launcher.py`
Expected: no output (function and all call sites removed).

- [ ] **Step 5: Update `.claude/CLAUDE.md`**

In the intro paragraph (around line 7), replace:
```
Sistema de facturación en Django para una práctica de psicología/servicios profesionales en Argentina, con emisión de comprobantes electrónicos (CAE) integrados a AFIP/ARCA. Un solo usuario administra los datos, pero la app es accesible desde otros dispositivos de la misma red local (ver "Acceso en red" abajo) — no hay servidor remoto ni multi-tenant.
```
with:
```
Sistema de facturación en Django para una práctica de psicología/servicios profesionales en Argentina, con emisión de comprobantes electrónicos (CAE) integrados a AFIP/ARCA. Un solo usuario administra los datos, accesible únicamente desde la misma PC (ver "Acceso en red" abajo para el porqué) — no hay servidor remoto ni multi-tenant.
```

Then replace the entire "Acceso en red" section (the paragraph starting `runserver` se levanta en \`0.0.0.0:8000\`... through ...solo cambia que la pantalla de login es alcanzable desde la LAN.\`, around lines 39-41) with:
```
### Acceso en red

Desde 2026-08-15 el servidor escucha en `127.0.0.1:8000` (no `0.0.0.0`): solo la propia PC puede conectarse. Antes aceptaba conexiones desde cualquier dispositivo de la LAN (celular, otra PC), pero sin HTTPS por delante el login y la cookie de sesión viajaban sin cifrar por la WiFi — un riesgo real para una app que emite comprobantes fiscales reales y expone datos de pacientes. Si en algún momento hace falta volver a abrir el acceso desde otros dispositivos, hay que ponerle TLS delante primero (certificado local + un servidor real, no `runserver`) y recién ahí volver a `0.0.0.0` en `launcher.py:levantar_servidor()`.

`facturacion/settings.py` sigue calculando `ALLOWED_HOSTS` dinámicamente con las IPs de LAN de la PC (función `_ips_lan_locales()`) — queda como código inofensivo mientras el bind sea `127.0.0.1`, no hace falta tocarlo.
```

- [ ] **Step 6: Commit**

```bash
git add launcher.py .claude/CLAUDE.md
git commit -m "fix(security): restringir el servidor a 127.0.0.1 (A1)"
```

---

### Task 2: A3 — Windows ACLs on secrets + cloud-sync warning

**Files:**
- Modify: `launcher.py`

**Interfaces:**
- Consumes: `BASE_DIR` (already defined at module level in `launcher.py`).
- Produces: two new functions, `asegurar_permisos_restringidos(ruta)` and `advertir_si_carpeta_sincronizada()`, called from `main()`. No other task depends on this one.

- [ ] **Step 1: Add `import os` to the top imports**

`launcher.py` currently imports `json, subprocess, sys, threading, time, urllib.request, webbrowser` but not `os`. Add `import os` to that import block (alphabetically, after `import json`).

- [ ] **Step 2: Add the two new functions**

Add these two functions to `launcher.py`, placed after `ip_lan` was removed (Task 1) — put them right before `def levantar_servidor():`:

```python
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
```

- [ ] **Step 3: Call both from `main()`**

In `main()`, right after the `if not MANAGE_PY.is_file():` block (so it runs even before the venv checks), add:
```python
    advertir_si_carpeta_sincronizada()
```

Then, right before the call to `levantar_servidor()` at the end of `main()`, add:
```python
    asegurar_permisos_restringidos(BASE_DIR / "certificados")
    asegurar_permisos_restringidos(BASE_DIR / "secret_key.txt")
    asegurar_permisos_restringidos(BASE_DIR / "db.sqlite3")
```

So the end of `main()` reads:
```python
    instalar_dependencias_si_hace_falta()
    aplicar_migraciones_si_hace_falta()
    asegurar_permisos_restringidos(BASE_DIR / "certificados")
    asegurar_permisos_restringidos(BASE_DIR / "secret_key.txt")
    asegurar_permisos_restringidos(BASE_DIR / "db.sqlite3")
    levantar_servidor()
```

- [ ] **Step 4: Verify syntax and manually exercise the new function**

Run: `"venv/Scripts/python.exe" -c "import ast; ast.parse(open('launcher.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

Then manually exercise `asegurar_permisos_restringidos` against a throwaway file (do NOT run this against the real `certificados/` folder or `db.sqlite3` — use a temp file so nothing in the real project is touched):
```bash
"venv/Scripts/python.exe" -c "
import sys
sys.path.insert(0, '.')
from pathlib import Path
import launcher
p = Path('./.superpowers/sdd/_icacls_test.txt')
p.write_text('test')
launcher.asegurar_permisos_restringidos(p)
print('no exception raised')
p.unlink()
"
```
Expected: `no exception raised` (importing `launcher.py` runs its module-level code, which is safe — it only defines `BASE_DIR` and constants, no side effects at import time). If `icacls` isn't available in this shell environment, the `subprocess.run` call will simply fail silently (it doesn't check the return code) — that's fine, note it in your report as a caveat: this step confirms the code runs without crashing, not that the ACL actually changed (verifying the actual permission change requires running the compiled `.exe` on a real Windows session, which is out of scope for this task — note this for manual follow-up).

- [ ] **Step 5: Commit**

```bash
git add launcher.py
git commit -m "fix(security): aplicar ACLs de Windows a certificados/secret_key/db (A3)"
```

---

### Task 3: A2 — Encrypt the SMTP password at rest

**Files:**
- Create: `arca/crypto.py`
- Create: `arca/migrations/0007_encrypt_email_password.py` (generated, not hand-written — see steps)
- Modify: `arca/models.py`
- Modify: `arca/admin.py`
- Modify: `arca/mailer.py`
- Modify: `arca/tests.py`

**Interfaces:**
- Produces: `arca/crypto.py` exports `cifrar(texto_plano: str) -> str` and `descifrar(texto_cifrado: str) -> str`. Both return `''` for falsy/invalid input — never raise.
- Produces: `EmpresaConfig.email_password_plano` — a `@property` that decrypts the stored value, used only by `arca/mailer.py`.
- Consumes: `settings.SECRET_KEY` (already exists) to derive the encryption key — no new configuration.

- [ ] **Step 1: Write the failing tests for `arca/crypto.py`**

Add to `arca/tests.py` (append after the existing classes; add `from arca.crypto import cifrar, descifrar` to the imports at the top of the file):
```python
class CifradoPasswordTests(TestCase):
    def test_roundtrip(self):
        self.assertEqual(descifrar(cifrar('mi-clave-secreta')), 'mi-clave-secreta')

    def test_cifrar_vacio_devuelve_vacio(self):
        self.assertEqual(cifrar(''), '')
        self.assertEqual(cifrar(None), '')

    def test_descifrar_vacio_devuelve_vacio(self):
        self.assertEqual(descifrar(''), '')
        self.assertEqual(descifrar(None), '')

    def test_descifrar_valor_invalido_devuelve_vacio(self):
        self.assertEqual(descifrar('esto-no-es-un-token-valido'), '')

    def test_dos_cifrados_del_mismo_texto_son_distintos(self):
        # Fernet incluye un IV aleatorio: no debe ser determinista.
        self.assertNotEqual(cifrar('hola'), cifrar('hola'))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `"venv/Scripts/python.exe" manage.py test arca.tests.CifradoPasswordTests`
Expected: `ModuleNotFoundError: No module named 'arca.crypto'`

- [ ] **Step 3: Implement `arca/crypto.py`**

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `"venv/Scripts/python.exe" manage.py test arca.tests.CifradoPasswordTests`
Expected: `Ran 5 tests in ...s OK`

- [ ] **Step 5: Write the failing tests for `EmpresaConfig.email_password_plano`**

Add to `arca/tests.py` (add `from arca.models import EmpresaConfig` to the imports at top if not already present):
```python
class EmpresaConfigEmailPasswordTests(TestCase):
    def test_email_password_plano_descifra(self):
        empresa = EmpresaConfig.get_config()
        empresa.email_password = cifrar('appsecret123')
        empresa.save(update_fields=['email_password'])
        self.assertEqual(empresa.email_password_plano, 'appsecret123')

    def test_email_password_plano_vacio_si_no_hay_password(self):
        empresa = EmpresaConfig.get_config()
        empresa.email_password = ''
        empresa.save(update_fields=['email_password'])
        self.assertEqual(empresa.email_password_plano, '')
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `"venv/Scripts/python.exe" manage.py test arca.tests.EmpresaConfigEmailPasswordTests`
Expected: `AttributeError: 'EmpresaConfig' object has no attribute 'email_password_plano'`

- [ ] **Step 7: Add the property to `EmpresaConfig` and bump `email_password`'s `max_length`**

In `arca/models.py`, change:
```python
    email_password = models.CharField(max_length=255, blank=True, null=True, verbose_name="Contraseña / clave de aplicación", help_text="Para Gmail, usar una 'contraseña de aplicación', no la contraseña normal de la cuenta")
```
to:
```python
    email_password = models.CharField(max_length=512, blank=True, null=True, verbose_name="Contraseña / clave de aplicación", help_text="Para Gmail, usar una 'contraseña de aplicación', no la contraseña normal de la cuenta. Se guarda cifrada.")
```
(512 because Fernet tokens are longer than the plaintext they encrypt — 255 could truncate a long app-password.)

Add this property to the `EmpresaConfig` class, near `email_from_header`:
```python
    @property
    def email_password_plano(self):
        """Descifra email_password para usarlo al conectar por SMTP
        (arca/mailer.py). Nunca usar email_password directo fuera de este
        modulo: siempre esta cifrado en la base."""
        from .crypto import descifrar
        return descifrar(self.email_password)
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `"venv/Scripts/python.exe" manage.py test arca.tests.EmpresaConfigEmailPasswordTests`
Expected: `Ran 2 tests in ...s OK`

- [ ] **Step 9: Generate and apply the migration (schema change + data migration)**

Run: `"venv/Scripts/python.exe" manage.py makemigrations arca`
Expected: a new migration file (e.g. `0007_alter_empresaconfig_email_password.py`) that alters `email_password`'s `max_length` to 512.

Now edit that generated migration file to also encrypt any existing plaintext value. Add this data-migration function near the top of the generated file (after the imports) and add a `migrations.RunPython(...)` operation after the `AlterField` operation:
```python
from arca.crypto import cifrar, descifrar


def cifrar_password_existente(apps, schema_editor):
    EmpresaConfig = apps.get_model('arca', 'EmpresaConfig')
    for config in EmpresaConfig.objects.all():
        valor = config.email_password
        if not valor:
            continue
        if descifrar(valor):
            continue  # ya esta cifrado (idempotente si se corre dos veces)
        config.email_password = cifrar(valor)
        config.save(update_fields=['email_password'])
```
Add `migrations.RunPython(cifrar_password_existente, migrations.RunPython.noop),` to the `operations` list, after the `AlterField` operation.

Run: `"venv/Scripts/python.exe" manage.py migrate arca`
Expected: `Applying arca.0007_...... OK`

- [ ] **Step 10: Write the failing tests for the admin form (before touching `arca/admin.py`)**

Add to `arca/tests.py` (add `from arca.admin import EmpresaConfigForm` to imports):
```python
class EmpresaConfigFormPasswordTests(TestCase):
    def _datos_minimos(self, **overrides):
        datos = {
            'razon_social': 'Test SRL', 'cuit': '20111222339',
            'condicion_iva': 'IVA Responsable Inscripto',
            'domicilio': 'Calle Falsa 123', 'localidad': 'CABA',
            'punto_venta_defecto': 1, 'otros_impuestos_pct': '0',
        }
        datos.update(overrides)
        return datos

    def test_dejar_en_blanco_preserva_password_existente(self):
        empresa = EmpresaConfig.get_config()
        empresa.email_password = cifrar('claveOriginal')
        empresa.save(update_fields=['email_password'])

        form = EmpresaConfigForm(data=self._datos_minimos(email_password=''), instance=empresa)
        self.assertTrue(form.is_valid(), form.errors)
        guardado = form.save()
        self.assertEqual(guardado.email_password_plano, 'claveOriginal')

    def test_escribir_nueva_password_la_cifra(self):
        empresa = EmpresaConfig.get_config()
        form = EmpresaConfigForm(data=self._datos_minimos(email_password='claveNueva'), instance=empresa)
        self.assertTrue(form.is_valid(), form.errors)
        guardado = form.save()
        self.assertEqual(guardado.email_password_plano, 'claveNueva')
        self.assertNotEqual(guardado.email_password, 'claveNueva')
```

- [ ] **Step 11: Run the tests to verify they fail**

Run: `"venv/Scripts/python.exe" manage.py test arca.tests.EmpresaConfigFormPasswordTests`
Expected: `test_dejar_en_blanco_preserva_password_existente` FAILS — the current form has no `clean_email_password`, so an empty submission overwrites `email_password` with `''` instead of preserving the existing cipher text. `test_escribir_nueva_password_la_cifra` FAILS too — the current form saves the typed password as plain text (not encrypted), so `guardado.email_password` already equals `'claveNueva'`, which fails the `assertNotEqual` check.

- [ ] **Step 12: Fix the admin form — never echo the password, encrypt on save**

In `arca/admin.py`, replace the whole `EmpresaConfigForm` class:
```python
class EmpresaConfigForm(forms.ModelForm):
    class Meta:
        model = EmpresaConfig
        fields = '__all__'
        widgets = {
            'email_password': forms.PasswordInput(render_value=True),
        }
```
with:
```python
class EmpresaConfigForm(forms.ModelForm):
    email_password = forms.CharField(
        required=False, widget=forms.PasswordInput(render_value=False),
        label='Contraseña / clave de aplicación',
        help_text="Para Gmail, usar una 'contraseña de aplicación'. Dejar en blanco para no cambiarla — nunca se muestra la guardada.",
    )

    class Meta:
        model = EmpresaConfig
        fields = '__all__'

    def clean_email_password(self):
        from .crypto import cifrar
        nuevo = self.cleaned_data.get('email_password', '').strip()
        if not nuevo:
            # Sin cambios: conservar el valor cifrado ya guardado.
            return self.instance.email_password
        return cifrar(nuevo)
```

- [ ] **Step 13: Run the tests to verify they pass**

Run: `"venv/Scripts/python.exe" manage.py test arca.tests.EmpresaConfigFormPasswordTests`
Expected: `Ran 2 tests in ...s OK`

- [ ] **Step 14: Update `arca/mailer.py` to use the decrypted accessor**

In `arca/mailer.py`, change:
```python
def conexion_smtp(empresa):
    return get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=empresa.email_host,
        port=empresa.email_port,
        username=empresa.email_remitente,
        password=empresa.email_password,
        use_tls=empresa.email_use_tls,
        timeout=TIMEOUT_SMTP_SEGUNDOS,
    )
```
to:
```python
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
```

- [ ] **Step 15: Run the full `arca` test suite**

Run: `"venv/Scripts/python.exe" manage.py test arca`
Expected: all tests pass, including the pre-existing `ImportarDbGuardasTests`/`EliminarBackupGuardasTests` (unaffected by this task) and the new ones from this task.

- [ ] **Step 16: Commit**

```bash
git add arca/crypto.py arca/models.py arca/admin.py arca/mailer.py arca/tests.py arca/migrations/
git commit -m "fix(security): cifrar la contraseña SMTP en reposo (A2)"
```

---

### Task 4: M4 — Validate the logo upload (extension + size)

**Files:**
- Modify: `arca/models.py`
- Modify: `arca/tests.py`

**Interfaces:**
- Produces: `EmpresaConfig.logo` now rejects (via `full_clean()`/`ModelForm.is_valid()`) files with an extension outside `png/jpg/jpeg/webp`, or larger than 5 MB.

- [ ] **Step 1: Write the failing tests**

Add to `arca/tests.py` (add `import base64`, `from io import BytesIO`, `from django.core.files.uploadedfile import SimpleUploadedFile` if not already imported, `from django.core.exceptions import ValidationError`, and `from PIL import Image` to the imports at top):
```python
class LogoValidacionTests(TestCase):
    def test_extension_invalida_rechazada(self):
        empresa = EmpresaConfig.get_config()
        empresa.logo = SimpleUploadedFile('logo.html', b'<html></html>', content_type='text/html')
        with self.assertRaises(ValidationError):
            empresa.full_clean()

    def test_extension_valida_aceptada(self):
        png_1x1 = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
        )
        empresa = EmpresaConfig.get_config()
        empresa.logo = SimpleUploadedFile('logo.png', png_1x1, content_type='image/png')
        empresa.full_clean()  # no debe lanzar

    def test_archivo_muy_grande_rechazado(self):
        # Ruido aleatorio: no comprime bien en PNG, asegura que el archivo
        # resultante realmente supere el limite (una imagen de color solido
        # comprimiria a unos pocos KB y el test no probaria nada real).
        import os as os_module
        ruido = os_module.urandom(1600 * 1600 * 3)
        img = Image.frombytes('RGB', (1600, 1600), ruido)
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        contenido = buffer.getvalue()
        self.assertGreater(len(contenido), 5 * 1024 * 1024, "el PNG de prueba debe superar el limite para que el test tenga sentido")

        empresa = EmpresaConfig.get_config()
        empresa.logo = SimpleUploadedFile('logo.png', contenido, content_type='image/png')
        with self.assertRaises(ValidationError):
            empresa.full_clean()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `"venv/Scripts/python.exe" manage.py test arca.tests.LogoValidacionTests`
Expected: `test_extension_invalida_rechazada` and `test_archivo_muy_grande_rechazado` FAIL (no `ValidationError` raised — the current field has no such validators); `test_extension_valida_aceptada` should already PASS (nothing rejects a valid PNG today).

- [ ] **Step 3: Add the validators to `EmpresaConfig.logo`**

In `arca/models.py`, add near the top of the file (after `from django.db import models`):
```python
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

LOGO_TAMANO_MAXIMO_MB = 5


def validar_tamano_logo(value):
    if value.size > LOGO_TAMANO_MAXIMO_MB * 1024 * 1024:
        raise ValidationError(f"El logo no puede superar los {LOGO_TAMANO_MAXIMO_MB} MB.")
```

Change:
```python
    logo = models.ImageField(
        upload_to='empresa/', blank=True, null=True,
        verbose_name="Logo",
        help_text="Tamaño sugerido: 400×160 px (relación 2.5:1), PNG con fondo transparente, para que se vea nítido en el comprobante impreso."
    )
```
to:
```python
    logo = models.ImageField(
        upload_to='empresa/', blank=True, null=True,
        verbose_name="Logo",
        help_text="Tamaño sugerido: 400×160 px (relación 2.5:1), PNG con fondo transparente, para que se vea nítido en el comprobante impreso. Máx. 5 MB.",
        validators=[
            FileExtensionValidator(allowed_extensions=['png', 'jpg', 'jpeg', 'webp']),
            validar_tamano_logo,
        ],
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `"venv/Scripts/python.exe" manage.py test arca.tests.LogoValidacionTests`
Expected: `Ran 3 tests in ...s OK`

- [ ] **Step 5: Generate and apply the migration**

Django generates a migration when a field's `validators` list changes (it's part of the field's deconstructed state).

Run: `"venv/Scripts/python.exe" manage.py makemigrations arca`
Expected: a new migration altering `logo`'s validators (e.g. `0008_alter_empresaconfig_logo.py` — the exact number depends on Task 3's migration having landed first).

Run: `"venv/Scripts/python.exe" manage.py migrate arca`
Expected: `Applying arca.0008_...... OK`

- [ ] **Step 6: Run the full `arca` test suite**

Run: `"venv/Scripts/python.exe" manage.py test arca`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add arca/models.py arca/tests.py arca/migrations/
git commit -m "fix(security): validar extension y tamano del logo (M4)"
```

---

### Task 5: M3 — Stop logging patient-identifying data, add log rotation, document M5

**Files:**
- Modify: `arca/wsfe.py`
- Modify: `facturacion/settings.py`
- Modify: `arca/config.py`

**Interfaces:**
- Produces: the two AFIP request/response log lines in `arca/wsfe.py` move from `logger.info` to `logger.debug` (and therefore stop appearing in `logs/arca_emisiones.log`, since that logger's configured level is `INFO`). Both `logs/arca_emisiones.log` and `logs/django_errors.log` rotate at 5 MB, keeping 5 backups, instead of growing forever.

- [ ] **Step 1: Downgrade the two PII-bearing log lines in `arca/wsfe.py`**

Change (around line 172):
```python
    logger.info("FECAESolicitar entorno=%s PtoVta=%s CbteTipo=%s detalle=%s", datos['entorno'], factura.punto_venta, factura.tipo_comprobante, detalle)
```
to:
```python
    logger.debug("FECAESolicitar entorno=%s PtoVta=%s CbteTipo=%s detalle=%s", datos['entorno'], factura.punto_venta, factura.tipo_comprobante, detalle)
```

Change (around line 182):
```python
    logger.info("FECAESolicitar respuesta cruda entorno=%s: %s", datos['entorno'], response)
```
to:
```python
    logger.debug("FECAESolicitar respuesta cruda entorno=%s: %s", datos['entorno'], response)
```

- [ ] **Step 2: Add rotation to both file handlers in `facturacion/settings.py`**

In the `LOGGING` dict, change:
```python
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
```
to:
```python
    'handlers': {
        'arca_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'arca_emisiones.log',
            'formatter': 'verbose',
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
        },
        'django_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'django_errors.log',
            'formatter': 'verbose',
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
        },
    },
```

- [ ] **Step 3: Document M5 as a conscious decision in `arca/config.py`**

In `arca/config.py`, find the `_AfipSSLAdapter` class docstring:
```python
class _AfipSSLAdapter(HTTPAdapter):
    """Adaptador HTTPS que permite cifrados/DH viejos, requeridos por los
    servidores de AFIP (rechazados por defecto en OpenSSL 3.x con el error
    'DH_KEY_TOO_SMALL'). Solo se usa para conectar a AFIP, no afecta al
    resto del sistema."""
```
Replace with:
```python
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
```

- [ ] **Step 4: Verify settings still load correctly**

Run: `"venv/Scripts/python.exe" manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Run the full test suite**

Run: `"venv/Scripts/python.exe" manage.py test`
Expected: all tests pass (this task has no dedicated new tests — it's a logging-level and config change with no branching logic to unit-test; correctness is verified by `manage.py check` succeeding and the full suite still passing).

- [ ] **Step 6: Commit**

```bash
git add arca/wsfe.py facturacion/settings.py arca/config.py
git commit -m "fix(security): dejar de loguear datos de pacientes, rotar logs, documentar M5 (M3)"
```

---

### Task 6: M2 — Require re-authentication before backup export/import

**Files:**
- Modify: `arca/views.py`
- Modify: `arca/templates/arca/backup.html`
- Modify: `arca/tests.py`

**Interfaces:**
- Produces: `exportar_db` and `importar_db` both now require a POST field `clave_confirmacion` matching the logged-in user's current password (via `request.user.check_password(...)`) before doing anything. `guardar_backup_local` (writes a copy to local disk only, not an exfiltration/persistence vector) is unchanged — out of scope, per the finding.

- [ ] **Step 1: Update the existing `ImportarDbGuardasTests` to account for the new password gate**

In `arca/tests.py`, the existing `ImportarDbGuardasTests` class currently doesn't send a `clave_confirmacion` field. Once Step 3 below adds the gate, every existing test in that class except `test_sin_login_redirige` and `test_get_no_permitido` would start failing for the wrong reason (rejected for missing password instead of what they're actually testing). Update the class now, before implementing the view change, so the test suite documents the new contract:

Replace the whole `ImportarDbGuardasTests` class with:
```python
class ImportarDbGuardasTests(TestCase):
    """La restauración de la base exige re-autenticación y confirmación explícita del servidor."""

    def setUp(self):
        self.password = 'clave-de-test'
        self.user = User.objects.create_user('tester', password=self.password)
        self.client.force_login(self.user)
        self.url = reverse('importar_db')

    def test_sin_login_redirige(self):
        self.client.logout()
        respuesta = self.client.post(self.url, {})
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/accounts/login/', respuesta['Location'])

    def test_get_no_permitido(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 405)

    def test_sin_password_rechazado(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(),
            'confirmacion': 'RESTAURAR',
        }, follow=True)
        self.assertContains(respuesta, 'Contraseña incorrecta')

    def test_password_incorrecta_rechazada(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(),
            'confirmacion': 'RESTAURAR',
            'clave_confirmacion': 'no-es-la-clave',
        }, follow=True)
        self.assertContains(respuesta, 'Contraseña incorrecta')

    def test_sin_confirmacion_rechazado(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(),
            'clave_confirmacion': self.password,
        }, follow=True)
        self.assertContains(respuesta, 'RESTAURAR')

    def test_confirmacion_incorrecta_rechazada(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(),
            'confirmacion': 'restaurar ya',
            'clave_confirmacion': self.password,
        }, follow=True)
        self.assertContains(respuesta, 'RESTAURAR')

    def test_extension_invalida_rechazada(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(nombre='cualquiercosa.txt'),
            'confirmacion': 'RESTAURAR',
            'clave_confirmacion': self.password,
        }, follow=True)
        self.assertContains(respuesta, '.sqlite3')

    def test_contenido_no_sqlite_rechazado(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(contenido=b'no soy una base de datos'),
            'confirmacion': 'RESTAURAR',
            'clave_confirmacion': self.password,
        }, follow=True)
        self.assertContains(respuesta, 'no es una base de datos SQLite')
```

Note: no test here actually completes a successful restore (that would overwrite the real `db.sqlite3` file on disk, since `importar_db` writes to `DB_PATH` directly rather than through Django's test-database isolation) — this matches the existing suite's own behavior, don't add one.

Also add a new test class for `exportar_db` (which has no existing tests) right after `ImportarDbGuardasTests`:
```python
class ExportarDbGuardasTests(TestCase):
    """La descarga de la base exige re-autenticación."""

    def setUp(self):
        self.password = 'clave-de-test'
        self.user = User.objects.create_user('tester2', password=self.password)
        self.client.force_login(self.user)
        self.url = reverse('exportar_db')

    def test_sin_login_redirige(self):
        self.client.logout()
        respuesta = self.client.post(self.url, {})
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/accounts/login/', respuesta['Location'])

    def test_get_no_permitido(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 405)

    def test_sin_password_rechazado(self):
        respuesta = self.client.post(self.url, {}, follow=True)
        self.assertContains(respuesta, 'Contraseña incorrecta')

    def test_password_incorrecta_rechazada(self):
        respuesta = self.client.post(self.url, {'clave_confirmacion': 'no-es-la-clave'}, follow=True)
        self.assertContains(respuesta, 'Contraseña incorrecta')

    def test_password_correcta_descarga(self):
        from django.conf import settings
        if not (settings.BASE_DIR / 'db.sqlite3').exists():
            self.skipTest('No hay db.sqlite3 en este entorno de test.')
        respuesta = self.client.post(self.url, {'clave_confirmacion': self.password})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/x-sqlite3')
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `"venv/Scripts/python.exe" manage.py test arca.tests.ImportarDbGuardasTests arca.tests.ExportarDbGuardasTests`
Expected: the `test_sin_password_rechazado` and `test_password_incorrecta_rechazada` tests in both classes FAIL (no such gate exists yet — the request currently proceeds past where the password check should stop it). The other tests in `ImportarDbGuardasTests` should still pass (they now include a correct password, so they reach the same validation logic as before).

- [ ] **Step 3: Implement the password gate in `arca/views.py`**

Add this helper function near the top of the "Backup y restauración" section (right after the `_listar_backups()` function):
```python
def _verificar_password(request):
    """Exige que el usuario re-tipee su contraseña de login antes de una
    accion de alto impacto (exportar/restaurar toda la base). Una sesion
    robada no alcanza sola para exfiltrar o reemplazar los datos."""
    clave = request.POST.get('clave_confirmacion', '')
    if not clave or not request.user.check_password(clave):
        messages.error(request, 'Contraseña incorrecta. Volvé a intentarlo.')
        return False
    return True
```

Then change `exportar_db`:
```python
@login_required
@require_POST
def exportar_db(request):
    """Descarga la DB actual como archivo sqlite3."""
    if not _verificar_password(request):
        return redirect('panel_backup')

    if not DB_PATH.exists():
```
(keep the rest of the function body exactly as-is, only the two lines above are new, inserted right after the docstring and before the existing `if not DB_PATH.exists():` check.)

And change `importar_db`:
```python
@login_required
@require_POST
def importar_db(request):
    """Restaura la DB desde un archivo subido por el usuario."""
    if not _verificar_password(request):
        return redirect('panel_backup')

    archivo = request.FILES.get('archivo_db')
```
(same pattern: two new lines inserted right after the docstring and before the existing `archivo = request.FILES.get('archivo_db')` line; the rest of the function is unchanged.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `"venv/Scripts/python.exe" manage.py test arca.tests.ImportarDbGuardasTests arca.tests.ExportarDbGuardasTests`
Expected: `OK` for all tests in both classes.

- [ ] **Step 5: Add the password field to both forms in `arca/templates/arca/backup.html`**

In the "Exportar base de datos" card, change:
```html
                    <form method="post" action="{% url 'exportar_db' %}">
                        {% csrf_token %}
                        <button type="submit" class="btn btn-primary"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3"/></svg> Descargar backup ahora</button>
                    </form>
```
to:
```html
                    <form method="post" action="{% url 'exportar_db' %}" style="display:flex; gap:8px; align-items:flex-end; flex-wrap:wrap;">
                        {% csrf_token %}
                        <div class="field" style="margin:0;">
                            <label for="clave_confirmacion_export">Confirmá tu contraseña</label>
                            <input type="password" id="clave_confirmacion_export" name="clave_confirmacion" required autocomplete="current-password">
                        </div>
                        <button type="submit" class="btn btn-primary"><svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3"/></svg> Descargar backup ahora</button>
                    </form>
```

In the "Restaurar base de datos" card, change:
```html
                <form method="post" action="{% url 'importar_db' %}" enctype="multipart/form-data"
                      onsubmit="return confirm('¿Seguro querés restaurar? Esto reemplaza toda la base de datos actual. Se guardará un backup automático antes de hacerlo.')">
                    {% csrf_token %}
                    <div class="field" style="max-width:420px;">
                        <label for="archivo_db">Archivo de backup (.sqlite3)</label>
                        <input type="file" id="archivo_db" name="archivo_db" accept=".sqlite3" required class="filter-search" style="cursor:pointer;">
                    </div>
                    <div class="field" style="max-width:420px; margin-top:12px;">
                        <label for="confirmacion">Escribí RESTAURAR para confirmar</label>
                        <input type="text" id="confirmacion" name="confirmacion" placeholder="RESTAURAR" required class="filter-search" autocomplete="off">
                    </div>
```
to:
```html
                <form method="post" action="{% url 'importar_db' %}" enctype="multipart/form-data"
                      onsubmit="return confirm('¿Seguro querés restaurar? Esto reemplaza toda la base de datos actual. Se guardará un backup automático antes de hacerlo.')">
                    {% csrf_token %}
                    <div class="field" style="max-width:420px;">
                        <label for="archivo_db">Archivo de backup (.sqlite3)</label>
                        <input type="file" id="archivo_db" name="archivo_db" accept=".sqlite3" required class="filter-search" style="cursor:pointer;">
                    </div>
                    <div class="field" style="max-width:420px; margin-top:12px;">
                        <label for="confirmacion">Escribí RESTAURAR para confirmar</label>
                        <input type="text" id="confirmacion" name="confirmacion" placeholder="RESTAURAR" required class="filter-search" autocomplete="off">
                    </div>
                    <div class="field" style="max-width:420px; margin-top:12px;">
                        <label for="clave_confirmacion_import">Confirmá tu contraseña</label>
                        <input type="password" id="clave_confirmacion_import" name="clave_confirmacion" required autocomplete="current-password">
                    </div>
```

- [ ] **Step 6: Run the full `arca` test suite**

Run: `"venv/Scripts/python.exe" manage.py test arca`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add arca/views.py arca/templates/arca/backup.html arca/tests.py
git commit -m "fix(security): exigir re-autenticacion para exportar/restaurar la base (M2)"
```

---

## Manual verification (after all 6 tasks)

Not automated — do by hand once everything is committed:

1. Recompile the exe (`pyinstaller --onefile --console --name FactuPsyware --icon static/img/icon.ico launcher.py`) and run it. Confirm the console no longer prints a LAN URL, and confirm from another device on the same network that `http://<LAN-ip>:8000/` is now unreachable (connection refused/times out).
2. Confirm `icacls certificados` (run manually in a terminal) shows only your Windows user with Full Control, no inherited broader permissions.
3. In `/admin/arca/empresaconfig/`, open the config, confirm the password field is blank (not pre-filled with dots representing the old value), type a new SMTP password, save, and confirm sending a test email from `/arca/verificacion/` still works (proves `email_password_plano` decrypts correctly).
4. Try uploading a `.html` file renamed to `.png` as the logo — confirm it's rejected. Upload a real PNG under 5 MB — confirm it works.
5. Open `logs/arca_emisiones.log` after emitting a test invoice — confirm the `detalle=`/`respuesta cruda` lines are gone (only INFO-level messages remain).
6. On `/arca/backup/`, try exporting or restoring without typing your password — confirm both are rejected with "Contraseña incorrecta." Try with the correct password — confirm both work as before.
