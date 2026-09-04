# Rediseño UI/UX del admin de Django

Partimos del admin 100% stock (ver [HANDOFF.md](../../../HANDOFF.md), puntos 6-8). Alcance: **solo `/admin/`**, no se toca `facturas/`/`servicios/` (ya tienen el tema "Legajo"). Principio: extender el esqueleto estándar de Django (header, sidebar de apps/modelos, listados, formularios con fieldsets), solo restylear con CSS — no reestructurar HTML/layout. Esto ya se acordó y se rechazó lo contrario en una sesión previa (ver historial en HANDOFF.md).

## Objetivo

Atractivo, consistente con el resto de la app, intuitivo y rápido de usar. Concretamente:

1. **Identidad visual**: cargar `theme.css`/`theme.js` en el admin, mapear variables de Django (`--header-bg`, `--primary`, etc.) a los tokens del proyecto, igual que se hizo antes. Esto además arregla las clases `.stamp-autorizada`/`.stamp-error`/etc. que ya usa `facturas/admin.py` y hoy se ven sin estilo.
2. **Jerarquía discreta**: encabezados de página (`h1`), de módulo (`h2`/`caption`) y de fieldset sin "caja" de color — solo borde inferior fino y peso de fuente, para que no compitan visualmente entre sí. Mismo criterio que se había validado antes del revert.
3. **Sidebar consistente**: la lista de apps/modelos a la izquierda debe verse igual en el dashboard que en el resto de páginas (Django por stock la oculta solo en `admin/index.html` vía `{% block nav-sidebar %}{% endblock %}` — hay que des-bloquearla ahí, como ya se había resuelto antes).
4. **Acceso rápido**:
   - Botón **"+ Nueva factura"** fijo en el header (junto al branding), visible en todas las pantallas del admin → `/admin/facturas/factura/add/`.
   - Link **"Facturación"** en la cinta superior (usertools), junto a "Ver sitio" / "Cambiar contraseña" / "Cerrar sesión" → `/facturas/`.
   - Resto del dashboard queda stock (lista de apps con Agregar/Cambiar) — no hay tarea dominante que priorizar, así que no se agregan cards ni atajos extra.
5. **Login del admin** (`/admin/login/`): mismo restyle que el resto, para que no haya salto visual respecto al login público (`/accounts/login/`).

## Archivos a tocar

- `templates/admin/base_site.html` (nuevo, recrear): branding + botón "Nueva factura", `extrahead` (theme.css/js), `extrastyle` (mapeo de variables + reglas monótonas de h1/h2/fieldset/sidebar/botones, igual base que antes), `usertools` (agregar link "Facturación").
- `templates/admin/index.html` (nuevo, recrear): solo lo mínimo para no bloquear `nav-sidebar`, sin agregar layout propio.
- No se toca ningún `admin.py` ni `arca/`.

## Verificación

`manage.py check` + `curl`/`django.test.Client` contra `/admin/login/`, `/admin/` y un changelist, confirmando 200 y presencia de las piezas clave (botón nueva factura, link facturación, theme.css). Sin navegador interactivo disponible — el usuario confirma visualmente en su PC.
