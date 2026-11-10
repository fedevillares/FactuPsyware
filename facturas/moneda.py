"""
Cálculo de importes de un comprobante con Decimal (nunca float) y soporte de
moneda extranjera.

Es la fuente de verdad de los totales de las facturas en dólares: el PDF, el
QR, el envío a ARCA (WSFE), el detalle, los reportes y el cálculo en vivo del
formulario (static/js/factura_totales.js, que replica este algoritmo con
enteros) salen todos de calcular_totales().

Reglas de redondeo (ROUND_HALF_UP, 2 decimales en importes):
  - subtotal de ítem   = redondear(cantidad × precio unitario)
  - IVA de ítem        = redondear(subtotal de ítem × alícuota / 100)
  - neto / IVA / total = sumas de los valores ya redondeados
  - equivalente en pesos (solo moneda extranjera):
        total en pesos = redondear(total × cotización)
        IVA en pesos   = redondear(IVA de cada alícuota × cotización)
        neto en pesos  = total en pesos − suma de IVA en pesos
    El neto en pesos sale por diferencia para que neto + IVA == total también
    en pesos (convertir cada parte por separado puede descuadrar $0,01).
"""
from decimal import Decimal, ROUND_HALF_UP

DOS_DECIMALES = Decimal('0.01')
SEIS_DECIMALES = Decimal('0.000001')

# Código AFIP de alícuota -> porcentaje
PORCENTAJES_IVA = {
    '3': Decimal('0'),
    '4': Decimal('10.5'),
    '5': Decimal('21'),
    '6': Decimal('27'),
    '8': Decimal('5'),
    '9': Decimal('2.5'),
}

# Moneda de la app -> datos para mostrar y para ARCA.
# 'arca' es el código de la tabla de monedas de ARCA (FEParamGetTiposMonedas).
MONEDAS = {
    'ARS': {'arca': 'PES', 'simbolo': '$', 'nombre': 'Pesos Argentinos'},
    'USD': {'arca': 'DOL', 'simbolo': 'US$', 'nombre': 'Dólar Estadounidense'},
}


def a_decimal(valor):
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def redondear(valor):
    """Importe a 2 decimales, ROUND_HALF_UP."""
    return a_decimal(valor).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)


def redondear_cotizacion(valor):
    """Cotización a 6 decimales (MonCotiz de ARCA admite 4 enteros + 6 decimales)."""
    return a_decimal(valor).quantize(SEIS_DECIMALES, rounding=ROUND_HALF_UP)


def subtotal_item(cantidad, precio_unitario):
    return redondear(a_decimal(cantidad) * a_decimal(precio_unitario))


def iva_item(subtotal, alicuota_iva):
    return redondear(a_decimal(subtotal) * PORCENTAJES_IVA[alicuota_iva] / Decimal('100'))


def calcular_totales(items, cotizacion=Decimal('1')):
    """
    `items`: iterable de objetos con cantidad, precio_unitario y alicuota_iva
    (FacturaItem o equivalente). `cotizacion`: pesos por 1 unidad de la moneda
    del comprobante (1 para pesos).

    Devuelve un dict con todos los importes en Decimal:
      neto, iva, total                  -> en la moneda del comprobante
      neto_ars, iva_ars, total_ars      -> equivalente en pesos
      alicuotas -> lista (de mayor a menor porcentaje, siempre las 6 de ARCA) de
                   {'codigo', 'porcentaje', 'base', 'iva', 'iva_ars'}
    """
    cotizacion = a_decimal(cotizacion)
    cero = Decimal('0.00')
    agrupado = {codigo: {'base': cero, 'iva': cero} for codigo in PORCENTAJES_IVA}

    for item in items:
        subtotal = subtotal_item(item.cantidad, item.precio_unitario)
        agrupado[item.alicuota_iva]['base'] += subtotal
        agrupado[item.alicuota_iva]['iva'] += iva_item(subtotal, item.alicuota_iva)

    alicuotas = [
        {
            'codigo': codigo,
            'porcentaje': PORCENTAJES_IVA[codigo],
            'base': datos['base'],
            'iva': datos['iva'],
            'iva_ars': redondear(datos['iva'] * cotizacion),
        }
        for codigo, datos in sorted(
            agrupado.items(), key=lambda kv: PORCENTAJES_IVA[kv[0]], reverse=True
        )
    ]

    neto = sum((a['base'] for a in alicuotas), cero)
    iva = sum((a['iva'] for a in alicuotas), cero)
    total = neto + iva

    total_ars = redondear(total * cotizacion)
    iva_ars = sum((a['iva_ars'] for a in alicuotas), cero)
    neto_ars = total_ars - iva_ars

    return {
        'neto': neto, 'iva': iva, 'total': total,
        'neto_ars': neto_ars, 'iva_ars': iva_ars, 'total_ars': total_ars,
        'alicuotas': alicuotas,
    }


def formato_ar(valor, decimales=2):
    """Formato argentino: punto de miles y coma decimal (1.234.567,89)."""
    valor = a_decimal(valor).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    signo = '-' if valor < 0 else ''
    entero, _, decimal = f"{abs(valor):f}".partition('.')
    entero = f"{int(entero):,}".replace(',', '.')
    return f"{signo}{entero},{decimal}" if decimales else f"{signo}{entero}"


def formato_cotizacion(valor):
    """Cotización en formato argentino: hasta 6 decimales, mínimo 2
    (1.570,00 / 1.435,125)."""
    entero, _, decimales = formato_ar(valor, 6).partition(',')
    return f"{entero},{decimales.rstrip('0').ljust(2, '0')}"
