# FactuPsyware

Sistema de facturación en Django para una práctica de psicología/servicios profesionales en Argentina, con emisión de comprobantes electrónicos (CAE) integrados a AFIP/ARCA. Uso local, un solo usuario por instancia, pensado para correr en la PC del consultorio sin servidor remoto.

## Cómo arrancar

No usar `python manage.py runserver` a mano salvo para debug puntual. El flujo normal del usuario es:

- `2 - Iniciar Facturacion.vbs` — uso diario, entorno de **homologación** (pruebas, no fiscal). Arranca oculto si el entorno ya está instalado; si no, abre una ventana visible con el progreso de instalación.
- `3 - Iniciar Facturacion (ENTORNO REAL).bat` — entorno de **producción**, factura contra AFIP real. Usar con cuidado.
- `1 - Instalar (solo la primera vez).bat` — fuerza una reinstalación completa del venv y dependencias.
- `0 - Si algo se cuelga, ejecutar esto.bat` — mata procesos `python.exe`/`pythonw.exe` colgados.
- `Resetear password admin.bat` — corre `manage.py changepassword admin` de forma interactiva.

Estos `.bat` son autoreparables: detectan si el venv está roto o incompleto (por ejemplo si la carpeta se copió desde otra PC/usuario) y lo recrean solos. Antes de tocar el venv siempre matan procesos Python colgados primero (causa típica de "Acceso denegado" al borrar/recrear).

El servidor corre en `http://127.0.0.1:8000/facturas/`. Logs en `server.log` (homologación) y `server_produccion.log` (producción).

## Estructura

- **`facturacion/`** — proyecto Django (settings, urls raíz, asgi/wsgi).
- **`clientes/`** — modelo `Cliente` (tipo/número de documento, condición de IVA).
- **`servicios/`** — modelo `Servicio` (ítems facturables, precio + alícuota de IVA).
- **`facturas/`** — modelo `Factura` (cabecera: cliente, tipo de comprobante, CAE, estado) y `FacturaItem` (líneas, calcula subtotal/IVA/total). Estados: `BORRADOR` → `AUTORIZADA` (con CAE) o `ERROR`.
- **`arca/`** — toda la integración con AFIP/ARCA. Es el corazón técnico del sistema:
  - `config.py` — credenciales y URLs por entorno (`datos_entorno('homologacion'|'produccion')`), más `get_zeep_client(wsdl_url)`, que **siempre** hay que usar en vez de `zeep.Client(...)` directo (ver nota SSL abajo).
  - `wsaa.py` — login WSAA: genera y firma el TRA (PKCS7/CMS con `cryptography`), cachea el token/sign en `certificados/ta_cache_<entorno>.json`.
  - `wsfe.py` — `solicitar_cae()` arma el detalle del comprobante y llama a `FECAESolicitar`; `ultimo_comprobante()` llama a `FECompUltimoAutorizado`.
  - `services.py` — `emitir_factura(factura)`, la función que orquesta todo desde la vista: autentica, pide CAE, actualiza el modelo `Factura`.
  - `diagnostico.py` — chequeos no destructivos por entorno (certificado legible, clave legible, correspondencia cert↔clave, WSFE alcanzable via `FEDummy`, login WSAA real). Alimenta el panel en `/arca/verificacion/`.
  - `models.py` — `EmpresaConfig`, singleton (siempre `pk=1`) con los datos de la empresa que van en el comprobante.

## Entornos AFIP

Se elige con la variable de entorno `ARCA_ENTORNO` (`homologacion` por defecto, o `produccion`). Cada entorno tiene su propio certificado, clave privada, URLs de WSAA/WSFE y caché de token, todo definido en `arca/config.datos_entorno()`. Los certificados viven en `certificados/`:

- Homologación: `certificado.crt` / `privada.key`.
- Producción: `FACTUPSYWARE_prod.crt` / `psywareprod.key`.

Panel de verificación en `/arca/verificacion/` muestra el estado de ambos entornos lado a lado (certificado, clave, correspondencia, conectividad WSFE, login WSAA).

## Detalle importante: SSL con AFIP

Los servidores de AFIP (`wsaa.afip.gov.ar`, `servicios1.afip.gov.ar`, etc.) usan parámetros Diffie-Hellman viejos que OpenSSL 3.x rechaza por defecto (`SSLError: DH_KEY_TOO_SMALL`). Por eso **todo** cliente SOAP contra AFIP debe crearse con `config.get_zeep_client(wsdl_url)`, que usa una `requests.Session` con un adaptador HTTPS en `SECLEVEL=1`. Nunca instanciar `zeep.Client(wsdl=...)` directo en este proyecto — si falta en algún lugar nuevo, es un bug.

## Errores de AFIP: dos niveles

La respuesta de `FECAESolicitar` puede traer el motivo del rechazo en dos lugares distintos:
- `response.Errors.Err` — errores generales (autenticación, formato del request, autorización del servicio). Si el rechazo viene por aquí, `FeDetResp` puede no tener `Observaciones`, lo que antes se mostraba como "Rechazado sin detalle" sin más información.
- `resultado.Observaciones.Obs` — errores específicos del comprobante (datos del cliente, importes, etc.).

`wsfe.solicitar_cae()` ya revisa ambos. Si en algún punto vuelve a aparecer "Rechazado sin detalle", revisar qué trae `response` completo (se vuelca en el mensaje de error como último recurso).

## Problemas recurrentes ya resueltos (no reintroducir)

- **`requirements.txt` en UTF-16**: si se reescribe con PowerShell (`pip freeze > requirements.txt`) puede volver a guardarse en UTF-16 y romper `pip install -r` con errores `Invalid requirement` llenos de bytes nulos. Verificar siempre con `file requirements.txt` → debe decir "ASCII text" o "UTF-8".
- **venv no portable**: `pyvenv.cfg` tiene rutas absolutas atadas al usuario/PC donde se creó. Copiar la carpeta del proyecto a otra PC rompe el venv. Los lanzadores ya detectan esto (intentan `import django` dentro del venv) y lo recrean solos.
- **"Acceso denegado" al recrear el venv**: pasa cuando un proceso Python anterior quedó con archivos del venv abiertos. Los lanzadores matan `python.exe`/`pythonw.exe` *antes* de tocar el venv, no después.

## Convenciones

- Comentarios y mensajes de usuario en español (Argentina).
- Modelos usan `@property` para cálculos derivados (subtotal, IVA, total) en vez de guardarlos en la base — recalculan siempre desde los ítems.
- Alícuotas de IVA representadas como códigos AFIP (`'3'`=0%, `'4'`=10.5%, `'5'`=21%, `'6'`=27%, `'8'`=5%, `'9'`=2.5%), no como porcentajes directos.
