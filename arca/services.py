from datetime import datetime
from . import wsaa, wsfe


def emitir_factura(factura):
    """
    Emite una factura contra ARCA: autentica, solicita CAE y actualiza el modelo.
    Devuelve (exito: bool, mensaje: str)
    """
    if factura.estado == 'AUTORIZADA':
        return False, 'La factura ya fue autorizada previamente.'

    if not factura.items.exists():
        return False, 'La factura no tiene items.'

    try:
        token, sign = wsaa.autenticar()
        resultado = wsfe.solicitar_cae(token, sign, factura)
    except Exception as e:
        return False, f'Error de conexión con ARCA: {e}'

    if resultado['ok']:
        factura.numero = resultado['numero']
        factura.cae = resultado['cae']
        factura.cae_vencimiento = datetime.strptime(resultado['cae_vencimiento'], '%Y%m%d').date()
        factura.estado = 'AUTORIZADA'
        factura.save()
        return True, f"Factura autorizada. CAE: {factura.cae}"
    else:
        factura.estado = 'ERROR'
        factura.observaciones = resultado['error']
        factura.save()
        return False, f"Error de ARCA: {resultado['error']}"