# Admin: aquietar encabezados grandes

Continuación de [HANDOFF.md](../../../HANDOFF.md). Solo CSS dentro de `templates/admin/base_site.html` (bloque `extrastyle`), sin tocar HTML/layout ni `arca/`.

## Problema

Tres encabezados del admin pesan visualmente más de lo necesario aunque ya están en paleta monótona (sesión anterior):

1. `<h1>` de página (título "Clientes", "Agregar cliente", etc.) — serif Lora 20px, sin tope propio, mucho margen inferior.
2. Fieldset legends en formularios ("DATOS GENERALES", etc.) — heredan colores monótonos pero conservan caja con borde/padding de Django stock.
3. Captions de módulo del dashboard ("CLIENTES", "FACTURAS") — mayúsculas + letter-spacing, compiten con el h1.

## Cambio

Todo en `templates/admin/base_site.html` (bloque `extrastyle`):

- `#content-main h1, .dashboard h1`: `font-size: 16px`, `font-weight: 600`, `text-transform: none`, `margin-bottom: 10px`.
- `fieldset .fieldset-heading, fieldset .inline-heading, :not(.inline-related) .collapse summary`: mismo tratamiento monótono que ya tienen `.module h2`/caption — fondo = `--bg-card`, sin borde propio, solo `border-bottom: 1px solid var(--border)`, `font-size: 12px`, sin caja.
- Captions de dashboard (`.dashboard .module caption`, ya cubiertas por la regla existente de `.module h2`/caption): bajar `letter-spacing` a `0.02em` y sacar `text-transform: uppercase` (queda en minúsculas/normal, peso 600 para diferenciarse igual).

## Verificación

`manage.py check` + `django.test.Client` (como en sesiones previas, sin navegador disponible). El usuario confirma visualmente en su propia PC.
