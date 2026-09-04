import logging
from datetime import datetime
from django.utils import timezone
from . import config, wsaa, wsfe

logger = logging.getLogger('arca')


def emitir_factura(factura, entorno):
    """
    Emite una factura contra ARCA en el entorno indicado ('homologacion' o
    'produccion'): autentica, solicita CAE y actualiza el modelo.
    Devuelve (exito: bool, mensaje: str)

    Usa un "claim" atómico (UPDATE condicional) sobre el estado antes de
    llamar a ARCA para que dos submits concurrentes de la misma factura
    (doble clic, reintento tras timeout) no puedan pedir CAE dos veces:
    solo uno de los dos consigue pasar estado BORRADOR/ERROR -> EMITIENDO,
    el otro se entera de que ya hay una emisión en curso y no llama a ARCA.
    """
    Factura = factura.__class__
    datos = config.datos_entorno(entorno)

    if factura.estado == 'AUTORIZADA':
        return False, 'La factura ya fue autorizada previamente.'

    if not factura.items.exists():
        return False, 'La factura no tiene items.'

    reclamado = Factura.objects.filter(
        pk=factura.pk, estado__in=['BORRADOR', 'ERROR']
    ).update(estado='EMITIENDO', actualizado=timezone.now())
    if not reclamado:
        factura.refresh_from_db()
        if factura.estado == 'AUTORIZADA':
            return False, 'La factura ya fue autorizada previamente.'
        return False, 'Esta factura ya se está emitiendo (otra pestaña o clic en curso). Esperá a que termine.'
    factura.estado = 'EMITIENDO'

    logger.info(
        "Emitiendo factura id=%s entorno=%s tipo=%s pto_vta=%s",
        factura.id, entorno, factura.tipo_comprobante, factura.punto_venta,
    )

    try:
        token, sign = wsaa.autenticar(datos)
        resultado = wsfe.solicitar_cae(token, sign, factura, datos)
    except Exception as e:
        logger.exception("Error de conexión con ARCA al emitir factura id=%s", factura.id)
        Factura.objects.filter(pk=factura.pk).update(
            estado='ERROR', error_arca=f'Error de conexión con ARCA: {e}',
            actualizado=timezone.now(),
        )
        return False, f'Error de conexión con ARCA: {e}'

    logger.info("Resultado solicitar_cae factura id=%s: %s", factura.id, resultado)

    if resultado['ok']:
        factura.numero = resultado['numero']
        factura.cae = resultado['cae']
        factura.cae_vencimiento = datetime.strptime(resultado['cae_vencimiento'], '%Y%m%d').date()
        factura.estado = 'AUTORIZADA'
        factura.entorno_emision = entorno
        try:
            factura.save()
        except Exception:
            # ARCA ya otorgó el CAE en este punto: si el guardado local falla,
            # NO hay que perder ese dato. Se deja constancia en el log con
            # todo lo necesario para completar el guardado a mano si hiciera
            # falta, en vez de devolver un 500 sin información recuperable.
            logger.exception(
                "CAE otorgado por ARCA pero fallo el guardado local. "
                "factura id=%s entorno=%s numero=%s cae=%s cae_vencimiento=%s — "
                "GUARDAR ESTOS DATOS MANUALMENTE, no volver a emitir.",
                factura.id, entorno, factura.numero, factura.cae, factura.cae_vencimiento,
            )
            return False, (
                f"ARCA otorgó el CAE {factura.cae} pero no se pudo guardar en el sistema. "
                f"No vuelvas a emitir esta factura: revisá logs/arca_emisiones.log y guardá el "
                f"número {factura.numero} y CAE {factura.cae} a mano."
            )
        logger.info(
            "Factura id=%s AUTORIZADA entorno=%s numero=%s cae=%s",
            factura.id, entorno, factura.numero, factura.cae,
        )
        return True, f"Factura autorizada. CAE: {factura.cae}"
    else:
        factura.estado = 'ERROR'
        factura.error_arca = resultado['error']
        factura.save()
        logger.warning("Factura id=%s ERROR entorno=%s: %s", factura.id, entorno, resultado['error'])
        return False, f"Error de ARCA: {resultado['error']}"
