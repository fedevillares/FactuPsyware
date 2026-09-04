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
