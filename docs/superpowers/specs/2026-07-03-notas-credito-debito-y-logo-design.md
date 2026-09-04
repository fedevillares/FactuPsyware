# Notas de crédito/débito editables + logo de empresa configurable

## Contexto

Hoy "Generar Nota de Crédito/Débito" crea automáticamente un borrador copiando
todos los ítems de la factura original 1:1, y para modificarla (cambiar
cantidades, sacar o agregar ítems) hay que ir al panel de Django admin.
El logo del comprobante está fijo en `static/img/logo.png`.

## 1. Motivo de la nota

`Factura` gana dos campos:

- `motivo_nota` (choices, blank/null): `DESCUENTO_PARCIAL`, `DEVOLUCION_PARCIAL`,
  `ANULACION_TOTAL`, `ERROR_FACTURACION`, `OTRO`.
- `motivo_nota_detalle` (TextField, blank/null): texto libre opcional.

Solo tienen sentido en notas de crédito/débito. Se muestran:
- En la pantalla de detalle de la factura (info-grid), si están cargados.
- Impresos en el comprobante PDF, cerca del bloque "Comprobantes Asociados".

## 2. Pantalla "Editar nota" (`/facturas/<id>/nota/editar/`, `editar_nota`)

- `generar_nota` (vista existente) sigue creando el borrador igual que hoy,
  pero redirige a `editar_nota` en vez de `detalle_factura`.
- Acceso solo si `factura.es_nota_credito or factura.es_nota_debito` y
  `estado in ('BORRADOR', 'ERROR')`; si no, redirige a `detalle_factura`.
- GET: formulario con:
  - Selector de motivo + textarea de detalle.
  - Tabla de ítems existentes: cantidad, precio unitario y alícuota editables
    por fila, más un checkbox "Eliminar".
  - Botón "+ Agregar producto" (JS) que agrega una fila nueva con selector de
    servicio; al elegir un servicio autocompleta precio/alícuota vía el
    endpoint ya existente `/servicios/datos/<id>/` (mismo patrón que
    `static/js/factura_item_admin.js`, usado hoy en el inline del admin).
- POST: parsea los campos indexados por id de ítem existente
  (`cantidad_<id>`, `precio_unitario_<id>`, `alicuota_iva_<id>`,
  `eliminar_<id>`) y las filas nuevas como listas paralelas
  (`nuevo_servicio[]`, `nueva_cantidad[]`, `nuevo_precio[]`,
  `nueva_alicuota[]`). Actualiza/borra/crea `FacturaItem` en una transacción;
  si la nota queda sin ítems, no guarda y vuelve a mostrar el formulario con
  un error. Guarda motivo + detalle. Redirige a `detalle_factura`.
- `detalle_factura`: agrega un botón "Editar nota" (visible solo si es nota y
  sigue en Borrador/Error) y muestra el motivo si está cargado.

No se toca la lógica de emisión (`emitir_factura`) ni el modelo `FacturaItem`
más allá de su uso normal ya existente.

## 3. Logo de empresa

- `EmpresaConfig.logo`: `ImageField(upload_to='empresa/', blank=True, null=True)`,
  con `help_text` indicando el tamaño sugerido: 400×160 px, PNG con fondo
  transparente (relación 2.5:1).
- `settings.py`: agrega `MEDIA_URL`/`MEDIA_ROOT`; `facturacion/urls.py` sirve
  `MEDIA_ROOT` (app de escritorio de un solo usuario, no hay razón para
  condicionar esto a `DEBUG`).
- `comprobante.html`: usa `empresa.logo.url` si existe; si no hay logo
  cargado, no muestra imagen (sin dependencia de que exista el archivo
  estático fijo).
- `arca/admin.py`: agrega `logo` al fieldset de "Datos fiscales".

## Fuera de alcance

- No se agrega un flujo de creación de facturas normales fuera del admin
  (sigue igual que hoy).
- No se valida que la cantidad devuelta no supere la original — queda a
  criterio del usuario, como cualquier otro campo de importe en el sistema.
