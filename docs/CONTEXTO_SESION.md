# Contexto de sesión — FactuPsyware

Complementa al `CLAUDE.md` del proyecto. Pegar ambos al inicio de una sesión nueva.

---

## Estado actual del código (al 2026-06-30)

### Cambios confirmados y verificados en esta sesión

#### `arca/wsfe.py` — bug crítico corregido
Antes mandaba `Concepto: 1` (Productos) fijo. El sistema factura **servicios**, lo que exige `Concepto: 2` y los campos `FchServDesde` / `FchServHasta` / `FchVtoPago` (sin ellos AFIP rechaza sin dar detalle claro).

Estado actual:
- `concepto = 2` fijo.
- Toma `periodo_desde` / `periodo_hasta` / `fecha_vto_pago` del modelo `Factura`. Si alguno es `None`, usa `date.today()` como fallback (AFIP exige el campo, no puede ir vacío).
- Para Notas de Crédito/Débito: agrega el bloque `CbtesAsoc` con tipo/punto de venta/número del comprobante original (`factura.factura_asociada`).
- Errores de AFIP se leen en **dos lugares** (`response.Errors.Err` para errores de cabecera, `resultado.Observaciones.Obs` para errores del comprobante). Antes solo se leía el segundo, lo que causaba "Rechazado sin detalle".

#### `facturas/models.py` — propiedad nueva
`Factura.desglose_iva` → lista de `{'porcentaje': float, 'importe': float}` agrupada por alícuota, ordenada de mayor a menor. La usa el template para mostrar el desglose IVA 21% / 10.5% / etc. que exige ARCA en el comprobante impreso.

#### `facturas/views.py` — dos cambios
1. `generar_nota()`: al crear la Nota de Crédito/Débito, copia `periodo_desde` / `periodo_hasta` / `fecha_vto_pago` de la factura original (antes quedaban vacíos, lo que rompía la validación de servicios al emitir).
2. `comprobante_preview()`: nueva vista en `/facturas/<id>/comprobante/preview/`. Renderiza el mismo `comprobante.html` para facturas sin CAE (BORRADOR/ERROR), pasando `es_preview=True` para mostrar un aviso rojo "VISTA PREVIA — sin validez fiscal" en lugar del CAE/QR real. No toca ARCA.

#### `facturas/urls.py` — URL nueva
```python
path('<int:factura_id>/comprobante/preview/', views.comprobante_preview, name='comprobante_preview'),
```

#### `facturas/templates/facturas/comprobante.html` — layout refactorizado
Cambios vs. la versión anterior:
- **Una sola copia** (ORIGINAL). Se eliminó el loop `{% for etiqueta in copias %}` que generaba ORIGINAL/DUPLICADO/TRIPLICADO.
- **Título dinámico**: `<h2>` ahora dice FACTURA / NOTA DE CRÉDITO / NOTA DE DÉBITO según `tipo_comprobante`. Antes decía "FACTURA" siempre fijo.
- **Bloque "Comprobantes Asociados"**: aparece si `factura.factura_asociada` existe. Obligatorio en Notas de Crédito/Débito según ARCA.
- **Tabla de ítems**: columnas correctas según PDF real de AFIP — Código, Producto/Servicio, Cantidad, U. medida, Precio Unit., % Bonif, Subtotal, Alicuota IVA, Subtotal c/IVA.
- **Totales**: Importe Neto Gravado + desglose IVA por alícuota (via `factura.desglose_iva`) + Importe Otros Tributos + Importe Total. Eliminado el bloque "Transparencia Fiscal Ley 27.743" que no corresponde al formato de comprobante.
- **CSS de impresión**: `@page { size: A4; margin: 10mm }`. En pantalla muestra borde/margen para previsualización; al imprimir queda A4 limpio sin borde.
- **Modo preview**: si el contexto trae `es_preview=True`, muestra aviso rojo en lugar de CAE/QR y oculta el bloque "Comprobante Autorizado".

#### `facturas/templates/facturas/detalle.html` — botón nuevo
En el bloque de borradores/error (junto a "Emitir" y "Eliminar borrador"):
```html
<a href="{% url 'comprobante_preview' factura.id %}" class="btn btn-outline" target="_blank">Vista previa del comprobante</a>
```
Funciona igual para facturas normales, notas de crédito y notas de débito en borrador.

---

## Bug de entorno conocido (sandbox Windows)

**Escrituras de archivos se truncan silenciosamente** cuando el archivo supera ~4-5 KB al escribirse desde el sandbox Linux hacia la carpeta Windows montada. `py_compile` no siempre lo detecta (una truncación en medio de un identificador puede ser Python válido hasta runtime). Patrón de verificación que funciona:

```python
# Verificar integridad después de cada edición grande:
content = open('archivo.py', 'rb').read()
print(len(content), content[-100:])
# + python3 -m py_compile archivo.py
```

**Fix cuando se trunca**: localizar el marcador de corte con `data.rfind(marker)`, reconstruir el resto como bytes literales, y escribir con `open(path, 'wb')`. Funciona con mayor fiabilidad que Edit/Write del sandbox para archivos grandes. Los archivos de texto pequeños (<~150 líneas) generalmente no se ven afectados.

---

## Arquitectura de los flujos principales

### Emitir factura (normal o Nota C/D)
```
views.emitir() [POST]
  → arca.services.emitir_factura(factura)
      → arca.wsaa.autenticar()          # token/sign, cacheado en certificados/ta_cache_<entorno>.json
      → arca.wsfe.solicitar_cae(token, sign, factura)
          → FECompUltimoAutorizado      # obtiene próximo número
          → FECAESolicitar              # manda el comprobante
          → lee response.Errors.Err     # errores de cabecera
          → lee resultado.Observaciones.Obs  # errores del comprobante
      → actualiza factura.numero / .cae / .cae_vencimiento / .estado
```

### Generar Nota de Crédito/Débito
```
views.generar_nota(factura_id, tipo_nota)
  → crea Factura(tipo=NC/ND, factura_asociada=original, copia periodo/vto)
  → copia todos los FacturaItem del original
  → redirect al detalle de la nota nueva (queda en BORRADOR)
  → el usuario la emite con el mismo botón "Emitir"
  → wsfe.solicitar_cae agrega CbtesAsoc automáticamente si factura_asociada existe
```

### Vista previa (sin CAE)
```
views.comprobante_preview(factura_id)
  → cualquier Factura (BORRADOR, ERROR, o incluso AUTORIZADA)
  → renderiza comprobante.html con es_preview=True, qr_b64=None
  → muestra aviso rojo, no genera QR, no toca ARCA
```

---

## Campos del modelo Factura relevantes para AFIP

| Campo | Uso en AFIP |
|---|---|
| `tipo_comprobante` | `CbteTipo` (1=FA, 6=FB, 11=FC, 3=NCA, 8=NCB, 2=NDA...) |
| `punto_venta` | `PtoVta` |
| `numero` | asignado por AFIP al autorizar, no antes |
| `periodo_desde` / `periodo_hasta` | `FchServDesde` / `FchServHasta` (obligatorio Concepto=2) |
| `fecha_vto_pago` | `FchVtoPago` (obligatorio Concepto=2) |
| `factura_asociada` | `CbtesAsoc` en NC/ND |
| `cliente.condicion_iva` | `CondicionIVAReceptorId` (RI=1, MONO=6, EX=4, CF=5) |
| `cliente.tipo_documento` | `DocTipo` (80=CUIT, 86=CUIL, 96=DNI, 99=CF sin ID → DocNro=0) |

---

## Pendiente / próximos pasos sugeridos

- **Confirmar con AFIP real**: hacer un test de emisión en homologación con la corrección de Concepto=2 + FchServ* para verificar que el "Rechazado sin detalle" histórico quedó resuelto. No fue confirmado aún contra ARCA real.
- **Cleanup**: el archivo `arca/_test_dummy.py` (contenido vacío/inofensivo, dejado por un test de sandbox) no pudo borrarse desde el sandbox por lock de Windows. Borrar manualmente desde el Explorador o con `0 - Si algo se cuelga, ejecutar esto.bat` previo.
- **Campos de período en admin**: `periodo_desde`, `periodo_hasta`, `fecha_vto_pago` ya están en `FacturaAdmin.fields` y son obligatorios para emitir correctamente. Si el usuario los deja vacíos, el sistema usa `date.today()` como fallback (funcional pero no ideal para facturación de períodos anteriores).
