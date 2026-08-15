# CRM (app `crm/`) — Diseño

Fecha: 2026-08-14

## Objetivo

Agregar una app `crm/` que unifique la relación con clientes (pipeline de leads +
ficha 360 de cliente) sin tocar `facturacion`, `facturas`, `clientes` ni `tickets`.
El CRM solo **lee** de esas apps para armar el timeline; la única escritura hacia
afuera es la creación de un `Cliente` al convertir un Lead.

## Modelos (`crm/models.py`)

### `Lead`
- `nombre` (CharField)
- `telefono` (CharField, blank/null)
- `email` (EmailField, blank/null)
- `origen` (CharField con choices: Referido, Redes, Web, Otro)
- `estado` (CharField con choices: NUEVO, CONTACTADO, NEGOCIACION, GANADO, PERDIDO; default NUEVO)
- `proximo_contacto` (DateField, blank/null)
- `cliente` (FK a `clientes.Cliente`, `on_delete=PROTECT`, blank/null — se completa al convertir)
- `creado` (DateTimeField, auto_now_add)
- `actualizado` (DateTimeField, auto_now) — mismo patrón que `Factura.actualizado`

### `NotaLead`
- `lead` (FK a `Lead`, `on_delete=CASCADE`, related_name `notas`)
- `texto` (TextField)
- `fecha` (DateTimeField, auto_now_add)

## Conversión Lead → Cliente

Vista `crm/views.py:convertir_lead`:
1. Formulario de alta de `Cliente` precargado con `nombre_completo`, `telefono`, `email` del Lead.
2. Al guardar: crea el `Cliente`, setea `lead.cliente = cliente`, `lead.estado = 'GANADO'`.
3. El Lead **no se borra** — queda como historial de origen del cliente.

No hay conversión inversa ni Leads retroactivos para clientes ya existentes: los
clientes actuales aparecen directo en la ficha 360 (sección siguiente), sin pasar
por el pipeline.

## Vistas

### Kanban de Leads (`/crm/`)
- Columnas: Nuevo, Contactado, En negociación, Ganado, Perdido.
- Tarjetas arrastrables (drag & drop nativo HTML5, sin librería nueva) que al
  soltarse hacen POST a un endpoint liviano (`/crm/leads/<id>/estado/`) que
  actualiza `estado` y devuelve 204. Mismo espíritu que el polling de
  `facturas/listado.html`, pero sin polling — solo el POST al soltar.
- Cada tarjeta: nombre, teléfono/email, próximo contacto si existe.
- Click en tarjeta → detalle del Lead (notas, botón "Convertir en Cliente").

### Detalle de Lead (`/crm/leads/<id>/`)
- Datos editables (nombre, teléfono, email, origen, próximo contacto).
- Bitácora de `NotaLead` (agregar nota con textarea + botón).
- Botón "Convertir en Cliente" (solo visible si `estado != GANADO`).

### Ficha 360 de Cliente (`/crm/clientes/<cliente_id>/`)
- Accesible desde el listado de `clientes/` (nuevo link) y desde el Lead ganado.
- Datos del cliente (lectura, iguales a los de `clientes/`).
- Timeline combinado, solo lectura, ordenado por fecha descendente:
  - Facturas del cliente (`factura.fecha_emision`, número, estado, total, link a `/facturas/<id>/`).
  - Tickets del cliente (`ticket.fecha` de apertura/eventos, estado, link a su detalle).
- Notas del CRM: si el cliente vino de un Lead ganado, muestra las `NotaLead` de ese lead.

## Fuera de alcance (explícito)

- Adjuntar archivos sueltos a un lead/cliente.
- Reportes o métricas de conversión del pipeline.
- Crear tickets desde el CRM.
- Leads retroactivos para clientes existentes.

## Integración con el resto del proyecto

- Nueva entrada de menú/navegación hacia `/crm/` (dónde exactamente, a definir en
  el plan de implementación revisando el template base actual).
- Migraciones propias de `crm/` (`0001_initial.py`), sin tocar migraciones de otras apps.
- Sigue las convenciones del proyecto: comentarios/UI en español, `@property`
  para cálculos derivados si hiciera falta, sin tocar el modelo `Cliente`.
