# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# FactuPsyware

Sistema de facturación en Django para una práctica de psicología/servicios profesionales en Argentina, con emisión de comprobantes electrónicos (CAE) integrados a AFIP/ARCA. Un solo usuario administra los datos, accesible únicamente desde la misma PC (ver "Acceso en red" abajo para el porqué) — no hay servidor remoto ni multi-tenant.

## Comandos de desarrollo

```bash
# Activar el entorno virtual (Windows)
venv\Scripts\activate

# Arrancar el servidor manualmente (solo para debug puntual)
python manage.py runserver 127.0.0.1:8000

# Migraciones
python manage.py migrate
python manage.py makemigrations

# Verificar que Django levanta sin errores
python manage.py check

# Resetear contraseña del admin
python manage.py changepassword admin

# Ver errores 500 del servidor (DEBUG=False en producción normal)
# Los errores se escriben en logs/django_errors.log.
# logs/server.log solo captura stdout (arranque/requests OK).
```

**No usar `python manage.py runserver` como flujo normal.** El flujo del usuario es siempre por `FactuPsyware.exe` (ver abajo).

## Lanzador (flujo normal del usuario)

Un solo ejecutable en la raíz: **`FactuPsyware.exe`**. Doble clic: mata procesos Python colgados, verifica/reconstruye `venv/` si falta o está roto, instala dependencias de `config/requirements.txt` si hace falta, corre migraciones pendientes, levanta el servidor y abre el navegador en `http://127.0.0.1:8000/facturas/`. Todo esto vive en `launcher.py` (compilado a `FactuPsyware.exe` con PyInstaller: `pyinstaller --onefile --console --name FactuPsyware --icon static/img/icon.ico launcher.py`, ejecutado desde la raíz del proyecto). Si se edita `launcher.py`, hay que recompilar el `.exe` para que el cambio tenga efecto — el `.exe` no lee `launcher.py` en tiempo de ejecución.

### Acceso en red

Desde 2026-08-15 el servidor escucha en `127.0.0.1:8000` (no `0.0.0.0`): solo la propia PC puede conectarse. Antes aceptaba conexiones desde cualquier dispositivo de la LAN (celular, otra PC), pero sin HTTPS por delante el login y la cookie de sesión viajaban sin cifrar por la WiFi — un riesgo real para una app que emite comprobantes fiscales reales y expone datos de pacientes. Si en algún momento hace falta volver a abrir el acceso desde otros dispositivos, hay que ponerle TLS delante primero (certificado local + un servidor real, no `runserver`) y recién ahí volver a `0.0.0.0` en `launcher.py:levantar_servidor()`.

`facturacion/settings.py` sigue calculando `ALLOWED_HOSTS` dinámicamente con las IPs de LAN de la PC (función `_ips_lan_locales()`) — queda como código inofensivo mientras el bind sea `127.0.0.1`, no hace falta tocarlo.

En `Bat adicionales/` quedan utilitarios ocasionales que no dependen del entorno AFIP:

- `Si algo se cuelga.bat` — mata procesos `python.exe`/`pythonw.exe` colgados.
- `Resetear password admin.bat` — corre `manage.py changepassword admin` interactivo.

`launcher.py` es **autoreparable**: detecta venv roto (import django falla), mata procesos Python colgados, recrea el venv y reinstala dependencias solo. El marcador `venv\.deps_ok` (copia de `config/requirements.txt`) indica que las dependencias están al día.

El servidor corre en `http://127.0.0.1:8000/facturas/`. Logs en `logs/`: `server.log` (todo el tráfico, sin distinción de entorno AFIP), `django_errors.log` (errores 500), `arca_emisiones.log` (actividad AFIP). Rutas configuradas en `facturacion/settings.py` vía `LOG_DIR`.

**Ya no hay variable de entorno ni lanzador separado para homologación/producción** (ver sección "Entornos AFIP" abajo) — se eligen por factura, dentro de la propia app.

## Estructura

- **`config/requirements.txt`** — dependencias del venv. Los lanzadores lo referencian como `config\requirements.txt`, no `requirements.txt` a secas.
- **`docs/`** — documentación de contexto de sesiones anteriores (`CONTEXTO_SESION.md`, `HANDOFF.md`, `INFORME.txt`). No es documentación de usuario final.
- **`backups/`** — copias de seguridad manuales de `db.sqlite3` y exports de datos (`clientes.json`, `servicios.json`, etc.). No versionado en git.
- **`facturacion/`** — proyecto Django (settings, urls raíz). `DEBUG=False` por defecto; activar con `DJANGO_DEBUG=1`. Sirve estáticos siempre con `django.contrib.staticfiles.views.serve(insecure=True)` — no tocar esa línea de `urls.py` o el admin queda sin CSS.
- **`clientes/`** — modelo `Cliente` (tipo/número de documento, condición de IVA, dirección).
- **`servicios/`** — modelo `Servicio` (ítems facturables: nombre, descripción, precio, alícuota IVA).
- **`facturas/`** — modelo `Factura` + `FacturaItem`. Estados: `BORRADOR` → `AUTORIZADA` (con CAE) o `ERROR`. Las vistas `/comprobante/` y `/comprobante/preview/` sirven **PDF directo** (no HTML). El listado (`/facturas/`) hace polling cada 8s a `/facturas/firma/` (endpoint liviano basado en `Max(actualizado)` + `Count`) para detectar cambios hechos desde otro dispositivo/pestaña y refrescarse sola — si el usuario tiene una fila seleccionada o está escribiendo en el buscador, en vez de recargar sola muestra un aviso "Hay cambios nuevos" para no perderle el trabajo en curso. `actualizado` es `auto_now=True`: cualquier `factura.save(update_fields=[...])` que no incluya `'actualizado'` en la lista no dispara la detección de cambios para ese guardado — agregarlo siempre que se toque el modelo con `update_fields`.
- **`tickets/`** — sistema de soporte técnico simple: modelo `Ticket` (por `Cliente`) + `TicketEvento` (historial de cierres/reaperturas con motivo). Al cerrar/reabrir un ticket se redirige a una pantalla de notificación por email (editable antes de enviar) usando la misma cuenta SMTP de `EmpresaConfig` (`arca/mailer.py`, compartido con `facturas/emailing.py`).
- **`arca/`** — integración AFIP/ARCA:
  - `config.py` — `datos_entorno(entorno)` devuelve cert/clave/URLs para `'homologacion'` o `'produccion'`. No hay entorno global fijo por proceso: cada llamada a AFIP recibe su `entorno` explícito. Usar siempre `get_zeep_client(wsdl_url)` (nunca `zeep.Client(...)` directo — ver SSL abajo).
  - `wsaa.py` — login WSAA: firma TRA con PKCS7/CMS, cachea token en `certificados/ta_cache_<entorno>.json`. `autenticar(datos)` recibe el dict de `datos_entorno()` como parámetro obligatorio.
  - `wsfe.py` — `solicitar_cae(token, sign, factura, datos)` y `ultimo_comprobante(...)`, ambos reciben `datos` (de `datos_entorno()`) explícito. Concepto=2 (Servicios) fijo; incluye `FchServDesde/Hasta/VtoPago` y bloque `CbtesAsoc` para Notas de Crédito/Débito.
  - `services.py` — `emitir_factura(factura, entorno)`: orquesta autenticación + CAE + actualización del modelo para el `entorno` ('homologacion' o 'produccion') indicado.
  - `pdf_comprobante.py` — genera el PDF del comprobante con ReportLab usando posiciones absolutas medidas del PDF real de ARCA. Función principal: `generar_pdf(factura, empresa, otros_impuestos, qr_b64, es_preview) -> bytes`.
  - `qr.py` — `generar_qr_base64(factura)`: QR según RG 4291, base64 PNG.
  - `diagnostico.py` — chequeos no destructivos por entorno. Alimenta `/arca/verificacion/`.
  - `models.py` — `EmpresaConfig` singleton (pk=1): razón social, CUIT, domicilio, condición IVA, `nombre_fantasia` (nombre comercial para el encabezado del PDF), `otros_impuestos_pct`, `leyenda`.

## Generación de PDF (`arca/pdf_comprobante.py`)

El PDF replica el layout exacto del comprobante oficial emitido por ARCA. Coordenadas en puntos tipográficos (pt) medidas con pdfplumber sobre un PDF real. Página A4 = 595×842 pt, márgenes 14pt, ancho útil 567pt.

- **Columnas del encabezado**: izquierda (emisor) hasta x=268, central (letra A/B/C) hasta x=327, derecha (datos comprobante) hasta x=581.
- **Tabla de ítems**: 9 columnas con anchos fijos en pt sumando exactamente 567pt. El generador maneja wrap de descripciones largas y filas vacías mínimas para mantener el aspecto del PDF real.
- **Totales**: celda izquierda (Importe Otros Tributos) y celda derecha (Neto + desglose IVA por alícuota + Total). Siempre muestra las 6 alícuotas (0% a 27%), con $0 si no se usaron.
- **Preview**: si `es_preview=True`, muestra marca de agua roja diagonal y bloque de aviso en lugar del CAE/QR.

**CRÍTICO al escribir este archivo**: el sandbox Linux escribe en carpeta Windows montada y **trunca archivos grandes silenciosamente** (~4-5KB). Siempre escribir via script Python en `/tmp/` que abre y escribe el destino, nunca con Write/Edit directo sobre archivos >4KB. Verificar con `len(open(dest,'rb').read())` y `ast.parse()` después de cada escritura.

## Entornos AFIP

El entorno ('homologacion' o 'produccion') se elige **por factura, al emitirla**, no al arrancar el servidor. En la pantalla de detalle de la factura (`facturas/templates/facturas/detalle.html`), el formulario de "Emitir y obtener CAE" tiene un selector "Autorización de PRUEBA" / "Autorización REAL (AFIP)". Si se elige REAL, hay que escribir la palabra `REAL` en un campo de confirmación (validado en JS y de nuevo en el servidor, `facturas/views.py:emitir`) antes de que el POST se acepte — evita que un solo clic dispare una autorización fiscal real por error.

Certificados en `certificados/`:
- Homologación: `certificado.crt` / `privada.key`
- Producción: `FACTUPSYWARE_prod.crt` / `psywareprod.key`

**Importante**: la restricción de unicidad de `Factura` (`punto_venta`, `tipo_comprobante`, `numero`) incluye `entorno_emision`. Aun así, hay que usar un `punto_venta` distinto para homologación y para producción (en esta cuenta: homologación = 1, producción = 3) — son numeraciones independientes del lado de AFIP, y mezclar el mismo punto de venta entre entornos puede hacer que AFIP devuelva números que ya existen localmente para el otro entorno.

Panel de estado (solo lectura, no emite comprobantes) en `/arca/verificacion/`.

## SSL con AFIP

Los servidores AFIP usan DH keys antiguas que OpenSSL 3.x rechaza (`DH_KEY_TOO_SMALL`). **Siempre** usar `config.get_zeep_client(wsdl_url)` — nunca `zeep.Client(wsdl=...)` directo. Si falta en código nuevo, es un bug.

## Errores de AFIP: dos niveles

`FECAESolicitar` puede devolver el rechazo en:
- `response.Errors.Err` — errores generales (auth, formato). `FeDetResp` puede no tener `Observaciones` en este caso.
- `resultado.Observaciones.Obs` — errores del comprobante específico.

`wsfe.solicitar_cae()` revisa ambos. Si aparece "Rechazado sin detalle", revisar el `response` completo.

## Modelos: propiedades clave

`Factura`:
- `letra_comprobante` → 'A'/'B'/'C' según tipo
- `es_nota_credito` / `es_nota_debito` → bool
- `numero_completo` → `"00001-00000012"`
- `subtotal`, `total_iva`, `total` → recalculan desde ítems (no se guardan en DB)
- `desglose_iva` → lista `[{'porcentaje': float, 'importe': float}]` agrupada por alícuota, ordenada de mayor a menor, siempre 6 elementos (una por alícuota AFIP)
- `esta_vencida` → bool, True si no está `pagada` y `fecha_vto_pago` ya pasó
- `pagada`, `fecha_pago`, `retencion_iva`, `retencion_ganancias` → seguimiento interno de cobro, se cargan DESPUÉS de emitir vía `/facturas/<id>/cobro/` (`actualizar_cobro`). No son datos fiscales, no aparecen en el PDF ni se envían a ARCA.

`FacturaItem`:
- `alicuota_iva`: código AFIP como string (`'3'`=0%, `'4'`=10.5%, `'5'`=21%, `'6'`=27%, `'8'`=5%, `'9'`=2.5%)
- `subtotal`, `iva_monto`, `total` → `@property`, calculados desde cantidad × precio

## Problemas recurrentes ya resueltos (no reintroducir)

- **`config/requirements.txt` en UTF-16**: si se regenera con PowerShell puede quedar UTF-16 y romper `pip install -r`. Verificar con `file config/requirements.txt` → debe decir "ASCII text" o "UTF-8".
- **venv no portable**: `pyvenv.cfg` tiene rutas absolutas. `FactuPsyware.exe` detecta esto (intenta `import django`) y recrea el venv solo.
- **"Acceso denegado" al recrear venv**: proceso Python anterior con archivos abiertos. `FactuPsyware.exe` mata `python.exe`/`pythonw.exe` *antes* de tocar el venv.
- **`venv/` no se versiona ni se conserva entre limpiezas**: son ~9200 archivos regenerables (Django, zeep, lxml, reportlab, cryptography, Pillow). Se puede borrar tranquilamente para reducir el tamaño en disco — `FactuPsyware.exe` lo reconstruye solo la próxima vez que se abre (1-2 min, necesita internet esa vez).
- **Truncación silenciosa de archivos grandes en el sandbox**: ver nota en sección PDF arriba.
- **500 sin detalle**: `DEBUG=False` por defecto. Los errores van a `logs/django_errors.log` (logger `django.request` en settings). Si el log no existe, el servidor no se reinició con los cambios.

## Convenciones

- Comentarios y mensajes de usuario en español (Argentina).
- Modelos: `@property` para cálculos derivados, nunca guardarlos en la base.
- Alícuotas IVA: códigos AFIP como strings, no porcentajes directos.
- Singleton `EmpresaConfig`: siempre `pk=1`, acceder con `EmpresaConfig.get_config()`.
