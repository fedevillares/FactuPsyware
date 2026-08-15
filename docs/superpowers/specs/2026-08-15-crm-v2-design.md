# CRM v2 — Diseño

## 1. Actividades

Modelo `Actividad` en `crm/models.py`:
- `lead` FK a `Lead`, `related_name='actividades'`, `on_delete=CASCADE`
- `tipo`: choices `NOTA`/`LLAMADA`/`REUNION`, default `NOTA`
- `titulo`: CharField(200)
- `fecha`: DateField (cuándo pasó, si `hecha`, o cuándo vence, si no)
- `hecha`: BooleanField default False
- `recordatorio_enviado`: BooleanField default False
- `creado`: DateTimeField auto_now_add

Formulario único en `detalle_lead.html`: tipo, título, fecha, checkbox "Ya pasó". Bitácora del lead muestra notas + actividades intercaladas por fecha, con badge "Vencida" si `not hecha and fecha < hoy`.

Recordatorio: al abrir `/crm/` (dashboard), se buscan `Actividad.objects.filter(hecha=False, recordatorio_enviado=False, fecha__lte=hoy)`, se manda un mail por cada una vía `arca/mailer.py` (mismo patrón que `tickets/emailing.py`), se marca `recordatorio_enviado=True`. Si `empresa_tiene_email_configurado()` es False, no se manda nada (silencioso, no bloquea el dashboard).

## 2. Dashboard

`/crm/` pasa a ser el dashboard; el Kanban se muda a `/crm/pipeline/` (`kanban_leads` conserva su nombre de URL, cambia el path). Nueva vista `crm_dashboard` en `/crm/` (nombre de URL `crm_dashboard`).

Sub-nav de 2 pestañas (Dashboard/Pipeline) incluida como partial `crm/_subnav.html` en dashboard.html y kanban.html.

Contenido del dashboard:
- `stat-strip`: leads activos (no Ganado/Perdido), tasa de conversión (`Ganados / (Ganados + Perdidos)`, 0 si no hay ninguno de los dos), actividades vencidas hoy, próximos contactos vencidos.
- Tabla "Actividades y contactos vencidos": actividades vencidas + leads con `proximo_contacto < hoy` (no Ganado/Perdido), cada fila linkea al lead.
- Tabla "Top clientes por facturación": `Cliente` anotado con `Sum` de `factura.total` no es directo en SQL (total es property Python) — se computa en Python sobre facturas con `estado='AUTORIZADA'`, ordenado desc, top 10.

## 3. Ficha de cliente más rica

`stat-strip` en `ficha_cliente.html`: total facturado (suma de `factura.total` de facturas AUTORIZADA), facturas del año actual, tickets abiertos (`not esta_cerrado`), fecha de última factura.

Timeline: agregar importe (`evento.obj.total` para facturas) a la derecha de cada fila; agrupar visualmente por año con un separador cuando cambia (`{% ifchanged %}`); riel vertical con CSS (`border-left` en el `<ul>` + `::before` por ítem).

## 4. Kanban — hallazgos de UI pendientes

- `crm/detalle_lead.html`: `<select name="estado">` con los 5 estados, postea a `actualizar_estado_lead` (endpoint ya existe) — alternativa accesible al drag-and-drop.
- `kanban.html`: feedback visual de drag (`.dragging`, `.is-drop-target`), mensaje si falla el drop o si se suelta en GANADO (en vez de fallar en silencio).
- Buscador (`filter-bar` con input `q`) en `kanban_leads`, filtra por nombre/teléfono/email igual que `clientes/listado.html`.
- Estado vacío del pipeline si no hay ningún lead.
- Columnas GANADO/PERDIDO con `border-top` de color (`--success`/`--danger`); GANADO con `opacity:.75` en el body y texto "Se llega convirtiendo el lead en cliente".
- Badge de vencido en la card si `proximo_contacto < hoy`.
- 📅 emoji → SVG de calendario.
- `order_by` explícito en `kanban_leads` (`proximo_contacto`, `-actualizado`).
- `convertir_lead.html`: field-hint bajo tipo_documento/condición_iva.

## Fuera de alcance

Sin campos personalizados, sin adjuntos, sin oportunidades/deals como entidad aparte, sin drag-and-drop optimista (sigue recargando la página al soltar).
