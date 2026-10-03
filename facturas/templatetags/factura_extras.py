from django import template
from django.template.defaultfilters import floatformat

register = template.Library()


@register.filter
def moneda(value):
    """Formatea un importe como en el comprobante oficial: coma decimal,
    sin separador de miles (ej. 493300,00), igual al formato que usa ARCA."""
    if value is None:
        value = 0
    return floatformat(value, 2).replace('.', '')


@register.filter
def porcentaje(value):
    """Formatea un porcentaje de alícuota sin localizar (punto decimal),
    igual al formato que usa ARCA (ej. 10.5%, no 10,5%)."""
    return ('%g' % float(value))


@register.simple_tag
def resumen_cobros(facturas):
    """Resumen de cobros de una lista de comprobantes (reporte mensual).

    Se calcula acá, a partir de las facturas que la vista ya pasa, para que
    el bloque "Cobros del período" no dependa de variables extra en el
    contexto. Las notas de crédito no tienen seguimiento de cobro: no cuentan
    como pagadas ni como pendientes.
    """
    r = {
        'cantidad_pagadas': 0, 'neto_pagado': 0.0, 'iva_pagado': 0.0,
        'cantidad_pendientes': 0, 'neto_pendiente': 0.0, 'iva_pendiente': 0.0,
        'retenciones': 0.0,
    }
    for f in facturas or []:
        if f.es_nota_credito:
            continue
        if f.pagada:
            r['cantidad_pagadas'] += 1
            r['neto_pagado'] += f.subtotal
            r['iva_pagado'] += f.total_iva
            r['retenciones'] += float(f.retencion_iva) + float(f.retencion_ganancias)
        else:
            r['cantidad_pendientes'] += 1
            r['neto_pendiente'] += f.subtotal
            r['iva_pendiente'] += f.total_iva
    r['total_cobrado'] = r['neto_pagado'] + r['iva_pagado']
    r['total_a_cobrar'] = r['neto_pendiente'] + r['iva_pendiente']
    return r
