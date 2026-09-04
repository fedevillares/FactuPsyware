# Handoff — FactuPsyware (rediseño UI/UX)

Contexto de sesión para retomar el trabajo con otro modelo/chat. Leer también [CLAUDE.md](CLAUDE.md) (instrucciones del proyecto, arquitectura AFIP/ARCA, convenciones) — este documento es solo sobre el trabajo de UI en curso.

## Qué es esto

Django + AFIP/ARCA, uso local de un solo usuario (consultorio de psicología). No tocar nada de `arca/` sin cuidado: **"no hacer nada que pueda ser serio en AFIP"** es una restricción explícita del usuario — no se hizo ningún cambio a la lógica de facturación/AFIP en esta sesión, todo fue visual/admin.

## Estado actual (qué se hizo)

1. **Bug crítico resuelto**: con `DEBUG=False` (modo normal de uso), Django no servía `/static/`, así que la interfaz se veía sin estilos ("todo blanco"). Se agregó un `re_path` manual con `django.views.static.serve` en [facturacion/urls.py](facturacion/urls.py) que sirve `/static/` siempre, sin depender de `DEBUG`. **No tocar esto** — si vuelve a aparecer la interfaz sin estilos, revisar primero que este bloque siga ahí.

2. **Rediseño visual "Legajo"**: paleta papel hueso + verde botella, tipografía Lora (display) + Inter (body) + IBM Plex Mono (números). Todo en [static/css/theme.css](static/css/theme.css) vía custom properties (`--bg`, `--accent`, `--text`, etc.), con variante `[data-theme="dark"]`. Toggle de tema con `static/js/theme.js` (persiste en localStorage).

3. **Rediseño del panel admin de Django** ([templates/admin/base_site.html](templates/admin/base_site.html), `*/admin.py` de las 4 apps):
   - Fieldsets, badges de estado, columnas calculadas, autocomplete, búsqueda/filtros mejorados en `clientes/admin.py`, `facturas/admin.py`, `servicios/admin.py`, `arca/admin.py`.
   - El admin mapea sus variables de color propias (`--header-bg`, `--primary`, etc.) a los tokens de `theme.css` para que se vea consistente con el resto de la app.
   - [templates/admin/index.html](templates/admin/index.html): override mínimo del dashboard de Django — **importante**: NO bloquea `nav-sidebar`, así el sidebar izquierdo con la lista de apps/modelos aparece igual en el dashboard que en el resto de páginas (el template stock de Django lo oculta solo en el index; eso generaba la queja "no está ordenado como una lista").
   - Raíz del sitio (`/`) redirige a `/admin/`, no a `/facturas/` (pedido explícito del usuario).
   - Crear una factura desde el admin redirige automáticamente a la vista de detalle de facturas (`facturas/admin.py`, métodos `response_add`/`response_change`/`_redirigir_a_detalle`).

4. **Última pasada (recién hecha)**: el usuario pidió que la interfaz se sienta menos "sobrecargada" y que la cinta superior del admin use el color del tema en vez de una barra oscura invertida. Se hizo:
   - `#header` del admin: pasó de fondo oscuro invertido a `var(--bg-card)` con texto `var(--text)`/`var(--text-muted)`.
   - Menos sombras (`.module { box-shadow: none }`, solo borde fino), padding reducido en cards/tablas, tipografía más chica en tablas, sello "AUTORIZADA" simplificado (tenía doble anillo, ahora un solo borde).
   - Se consultó https://21st.dev como referencia de principios (espaciado generoso, componentes consistentes, ocultar lo secundario) — ya aplicado, no hace falta repetirlo.

## Historial de idas y vueltas (para no repetir errores)

El usuario rechazó dos intentos de rediseño del dashboard antes de llegar a la versión actual:
1. Dashboard tipo "hero" + grid de cards → rechazado ("mas ordenada, con filas a la izquierda, como el admin de Django").
2. Sidebar estilizado pero el dashboard seguía sin sidebar visible (por el comportamiento stock de Django) → rechazado de nuevo ("ordenado de forma vertical y a la izquierda, como una lista").
3. Fix final: dejar de bloquear `nav-sidebar` en `index.html` → el sidebar es consistente en todas las páginas. Esto parece haber resuelto el reclamo, pero no hubo confirmación explícita del usuario todavía — **verificar con el usuario si esto quedó bien antes de asumirlo cerrado**.

**Patrón a evitar**: no diseñar layouts "originales" para el admin de Django sin que el usuario lo pida explícitamente. Prefiere extender el comportamiento stock de Django y solo restylear con CSS (colores, tipografía, espaciado) en vez de reestructurar el HTML/layout.

5. **Encabezados grandes en el admin (este pase)**: el usuario pidió explícitamente "sacar los encabezados grandes". Diagnóstico y cambios en detalle: [docs/superpowers/specs/2026-06-30-admin-quiet-headers-design.md](docs/superpowers/specs/2026-06-30-admin-quiet-headers-design.md). Resumen: se redujo el `<h1>` de página (20px serif → 16px), se aplicó el mismo tratamiento monótono de los module h2 a los fieldset legends de los formularios (antes seguían en caja con borde de Django stock), y se sacaron mayúsculas/letter-spacing fuerte de los captions de módulo. Todo en `templates/admin/base_site.html` bloque `extrastyle`, sin tocar HTML/layout.

6. **Revert del restyle visual del admin (este pase)**: el usuario pidió volver a la interfaz original del admin de Django y partir de ahí — el punto 5 (encabezados grandes) quedó obsoleto, no reintentar esos ajustes sin que se pida de nuevo. Se borraron `templates/admin/base_site.html` y `templates/admin/index.html` (con `APP_DIRS=True`, Django cae solo en sus templates stock al no encontrarlos en la app). En `facturacion/urls.py` se sacó `admin.site.login = CustomLoginView.as_view()` para que `/admin/` use el login stock de Django en vez del template temático compartido — `CustomLoginView` sigue existiendo y se usa en `/accounts/login/`, que es el login del resto de la app (`facturas/`, etc.) y **no** se tocó: sigue con `theme.css` y el diseño "Legajo". El admin ahora es 100% stock salvo `site_header`/`site_title`/`index_title` (texto, no visual) y el orden de apps en el listado (`_APP_ORDER` en `urls.py`, funcional no visual). Se mantuvieron intactos los `admin.py` de las 4 apps (fieldsets, badges, autocomplete, búsqueda, filtros) por pedido explícito — eso no es "interfaz", es organización de datos.
   - **No tocar** el bloque de `re_path` para `/static/` en `urls.py` ni el redirect de `/` a `/admin/` — siguen vigentes y no son parte de este revert.

7. **Revert completo (este pase)**: el usuario pidió que el admin quede 100% como el default de Django, no solo sin CSS. Se sacaron de `facturacion/urls.py` también `admin.site.site_header`, `admin.site.site_title`, `admin.site.index_title` y el monkeypatch de orden de apps (`_get_app_list_ordenada`/`_APP_ORDER`). Verificado con curl que `/admin/login/` ahora dice "Administración de sitio Django" / "Administración de Django" (default), no "FactuPsyware". El servidor de homologación corre con `runserver` y autoreload, así que los cambios de código y templates se aplican solos (StatReloader reinicia el proceso) — **si después de un cambio se ve raro, probablemente es caché del navegador, no el servidor**: pedir un hard refresh (Ctrl+F5) antes de asumir que algo quedó mal.

8. **Bug encontrado y resuelto (este pase): admin sin CSS/JS propios de Django (todo texto plano, íconos rotos)**. Causa: el `re_path('^static/...')` en `facturacion/urls.py` servía `/static/` con `django.views.static.serve` apuntando solo a `BASE_DIR / 'static'` (nuestra carpeta con `theme.css`/`theme.js`/`img/`). Mientras el admin usaba templates custom que cargaban `theme.css`, alcanzaba para que se viera "vestido". Al volver a los templates stock del punto 7, esos piden `/static/admin/css/base.css`, `/static/admin/js/...`, etc. (los estáticos que trae `django.contrib.admin`, nunca copiados a `BASE_DIR/static`), y daban 404 → admin sin ningún estilo. **Fix**: se cambió a `django.contrib.staticfiles.views.serve` (basada en los finders de `STATICFILES_DIRS` + apps instaladas, incluye `django.contrib.admin`), con `insecure=True` porque esa vista por default solo corre si `DEBUG=True` y acá se corre con `DEBUG=False` a propósito. Verificado con curl: `/static/admin/css/base.css`, `/static/admin/css/nav_sidebar.css`, `/static/css/theme.css`, `/static/img/logo.png` devuelven 200. **No reintroducir** el `document_root` fijo a `static/` — rompe todo lo que no sea nuestro.

9. **Rediseño del admin sobre la base stock (este pase)**: recreados `templates/admin/base_site.html` y `templates/admin/index.html` siguiendo la spec [docs/superpowers/specs/2026-06-30-admin-redesign-design.md](docs/superpowers/specs/2026-06-30-admin-redesign-design.md). Resumen:
   - Vuelve a cargarse `theme.css`/`theme.js` en el admin (mapeo de variables Django → tokens del proyecto), igual criterio "monótono" de antes para h1/módulos/fieldsets.
   - `index.html` ya **no bloquea** `nav-sidebar` (a diferencia del stock de Django, que sí lo oculta solo en el dashboard) — el sidebar de apps/modelos es consistente en todas las páginas.
   - Botón **"+ Nueva factura"** fijo en el header (`#site-name`, junto al branding) → `/admin/facturas/factura/add/`, visible en todo el admin (incluido el login, antes de autenticarse — no rompe nada, solo redirige a login si se clickea sin sesión).
   - Link **"Facturación"** agregado al bloque `usertools` (cinta superior, junto a "Ver sitio"/"Cambiar contraseña"/"Cerrar sesión") → `/facturas/`.
   - El login del admin (`/admin/login/`) hereda el mismo restyle automáticamente porque `admin/login.html` (stock) extiende `admin/base_site.html` — no hizo falta tocar `CustomLoginView`.
   - No se tocó ningún `admin.py` ni `arca/`. Verificado con `manage.py check`, `curl` (login) y `django.test.Client` con `force_login()` (dashboard + changelist de facturas, ambos 200, con sidebar/botón/link/theme.css presentes).
   - Sigue sin haber navegador interactivo disponible en esta sesión — falta confirmación visual del usuario.

10. **Bugs de tipografía/contraste encontrados y resueltos con verificación visual real (Playwright)**: el usuario reportó "no me gusta la interfaz... revisa la tipografía sobre todo los colores... corrige las distancias y espacios". Se consiguió ver el admin autenticado con Playwright (método en la sección de abajo) y aparecieron 3 bugs reales que el chequeo por texto/curl de la sesión anterior no detectaba:
   - **Botones "Agregar"/"Modificar" con texto invisible**: `.object-tools a` heredaba `color: var(--accent)` (verde) de la regla genérica de links de `#content a, ...`, igual al `background: var(--object-tools-bg)` (también verde) del botón — texto verde sobre fondo verde. Esa regla genérica usa selectores con `#id` (especificidad alta); hubo que agregar `#content .object-tools a, #toolbar .object-tools a { color: var(--bg) !important; }` con esa misma especificidad para ganarle (una clase sola no alcanzaba).
   - **Nombres de modelo en mayúsculas y gris apagado, casi ilegibles**: theme.css trae una regla genérica `th { text-transform: uppercase; color: var(--text-muted); }` pensada para encabezados de tabla de datos. Django usa `<th>` también para los links principales de navegación (nombre de cada modelo) en el sidebar y en el listado de apps del dashboard — quedaban con el mismo tratamiento que un header de columna, en vez de leerse como lo que son: la navegación primaria del admin. Fix: `.module table th, #content-main .module th, .dashboard .module th { text-transform: none !important; color: var(--text) !important; ... }`.
   - **Mismo problema con los captions de grupo de apps en el sidebar** ("Autenticación y Autorización", "Clientes", etc.): el tratamiento "monótono" (sin mayúsculas, sin caja) ya se aplicaba a esos captions en el contenido principal (`.dashboard .module caption`) pero no a los del sidebar (`#nav-sidebar` no es descendiente de `.dashboard`/`#content`), así que el mismo texto se veía distinto en el sidebar que en el panel central. Se agregó `#nav-sidebar .module caption` a la misma regla monótona para que sea consistente en todas partes.
   - **Cinta de usuario (`#user-tools`) en mayúsculas con letter-spacing y borde blanco invisible**: eso es el CSS de fábrica de Django pensado para el header oscuro original; sobre el header claro quedaba apretado y difícil de leer. Se neutralizó `text-transform`/`letter-spacing` y se sacó el `border-bottom` blanco translúcido que no se veía contra el fondo claro.
   - Todo en `templates/admin/base_site.html`, bloque `extrastyle`. No se tocó layout/HTML, solo CSS.

## Pendiente / por confirmar con el usuario

- **Confirmar visualmente el punto 10** con el usuario en su PC (Ctrl+F5 si algo se ve raro por caché).
- Confirmar que el ajuste anterior de densidad/cinta superior en `facturas/`/`servicios/` (fuera del admin) sigue cumpliendo lo pedido (tampoco hubo confirmación explícita todavía).

## Cómo verificar cambios de UI visualmente (Playwright, sin credenciales reales)

Esta sesión consiguió ver el admin **autenticado** con Playwright sin manejar contraseñas reales ni forjar una sesión viva contra el servidor (eso último está prohibido — no generar/imprimir un `sessionid` real). El método:

1. Renderizar el HTML autenticado con `django.test.Client` + `force_login()` (corre en un proceso de test aislado, no expone cookies de sesión utilizables):
   ```python
   from django.test import Client
   from django.conf import settings
   from django.contrib.auth import get_user_model
   settings.ALLOWED_HOSTS.append('testserver')
   u = get_user_model().objects.filter(is_superuser=True).first()
   c = Client()
   c.force_login(u)
   html = c.get('/admin/').content.decode()
   # Insertar <meta charset="utf-8"> y <base href="http://127.0.0.1:8000/"> justo después de <head>
   # (el <base> hace que las requests de CSS/JS/imágenes salgan contra el server real corriendo;
   # esos assets son públicos, no requieren sesión. Sin <meta charset>, el navegador puede
   # adivinar mal el encoding y mostrar acentos rotos — no es un bug real, es un artefacto del método).
   ```
2. Guardar ese HTML en un archivo y servirlo con `python -m http.server <puerto>` desde esa carpeta (Playwright bloquea `file://` directamente).
3. Navegar ahí con `mcp__plugin_playwright_playwright__browser_navigate` y sacar screenshot con `browser_take_screenshot`, o usar `browser_run_code_unsafe` con `getComputedStyle(...)` para confirmar colores/contraste exactos en vez de adivinar por ojo (así se encontraron los 3 bugs del punto 10 — el de texto invisible no se nota a simple vista en una captura chica).
4. Recordar cerrar el `http.server` temporal al terminar (`taskkill /F /PID <pid>`).

Si en algún momento hay acceso a la extensión de Chrome o a un navegador con sesión real del usuario, preferir eso — este método es el fallback cuando no lo hay.

## Archivos clave tocados en esta sesión

- `facturacion/urls.py` — fix de static files + orden del admin + redirect raíz.
- `static/css/theme.css` — sistema de diseño completo.
- `static/js/theme.js` — toggle de tema claro/oscuro.
- `templates/admin/base_site.html` — todo el restyle del admin (header, sidebar, módulos).
- `templates/admin/index.html` — override mínimo del dashboard.
- `clientes/admin.py`, `facturas/admin.py`, `servicios/admin.py`, `arca/admin.py` — configuración de cada ModelAdmin.

## Convención del proyecto a respetar

Comentarios y mensajes en español (Argentina). Ver [CLAUDE.md](CLAUDE.md) para todo lo demás (entornos AFIP, estructura de apps, errores recurrentes ya resueltos que no hay que reintroducir).
