import datetime
import logging
from . import config

logger = logging.getLogger('arca')


def get_client(datos):
    return config.get_zeep_client(datos['wsfe_url'])


def ultimo_comprobante(token, sign, punto_venta, tipo_cbte, datos):
    """Consulta el último número de comprobante autorizado para un punto de venta y tipo."""
    client = get_client(datos)

    auth = {
        'Token': token,
        'Sign': sign,
        'Cuit': config.CUIT,
    }

    response = client.service.FECompUltimoAutorizado(
        Auth=auth,
        PtoVta=punto_venta,
        CbteTipo=tipo_cbte,
    )

    return response


def solicitar_cae(token, sign, factura, datos):
    """
    Solicita el CAE para una Factura (modelo de Django) ya con sus items cargados,
    contra el entorno indicado por `datos` (ver arca.config.datos_entorno).
    Devuelve un diccionario con 'cae', 'cae_vencimiento', 'numero' si fue exitoso,
    o 'error' con el detalle si falló.
    """
    client = get_client(datos)

    auth = {
        'Token': token,
        'Sign': sign,
        'Cuit': config.CUIT,
    }

    # 1. Obtener el próximo número de comprobante
    ultimo = client.service.FECompUltimoAutorizado(
        Auth=auth,
        PtoVta=factura.punto_venta,
        CbteTipo=int(factura.tipo_comprobante),
    )
    proximo_numero = ultimo.CbteNro + 1

    # 2. Armar el detalle de IVA agrupado por alícuota
    iva_agrupado = {}
    for item in factura.items.all():
        clave = item.alicuota_iva
        if clave not in iva_agrupado:
            iva_agrupado[clave] = {'BaseImp': 0, 'Importe': 0}
        iva_agrupado[clave]['BaseImp'] += item.subtotal
        iva_agrupado[clave]['Importe'] += item.iva_monto

    iva_array = [
        {
            'Id': int(alicuota),
            'BaseImp': round(datos['BaseImp'], 2),
            'Importe': round(datos['Importe'], 2),
        }
        for alicuota, datos in iva_agrupado.items()
    ]

    # Totales calculados desde el mismo desglose redondeado que se envía en
    # AlicIva: así ImpNeto == suma de BaseImp, ImpIVA == suma de Importe e
    # ImpTotal == ImpNeto + ImpIVA siempre. Redondear cada total por separado
    # desde los floats del modelo puede descuadrar $0,01 y AFIP rechaza el
    # comprobante por inconsistencia de importes.
    imp_neto = round(sum(d['BaseImp'] for d in iva_array), 2)
    imp_iva = round(sum(d['Importe'] for d in iva_array), 2)
    imp_total = round(imp_neto + imp_iva, 2)

    hoy = datetime.date.today().strftime('%Y%m%d')

    # 3. Determinar tipo y número de documento del cliente
    cliente = factura.cliente
    doc_tipo = int(cliente.tipo_documento)

    if doc_tipo == 99:
        doc_nro = 0
    else:
        doc_nro_str = cliente.numero_documento.replace('-', '').replace('.', '').strip()
        try:
            doc_nro = int(doc_nro_str) if doc_nro_str else 0
        except ValueError:
            return {
                'ok': False,
                'error': f"El número de documento del cliente '{cliente.nombre_completo}' "
                         f"('{cliente.numero_documento}') no es válido: debe contener solo dígitos.",
            }

    # 4. Condición frente al IVA del receptor (requerido por RG 5616)
    CONDICION_IVA_ARCA = {
        'RI': 1,
        'MONO': 6,
        'EX': 4,
        'CF': 5,
    }
    condicion_iva_receptor = CONDICION_IVA_ARCA.get(cliente.condicion_iva)
    if condicion_iva_receptor is None:
        return {
            'ok': False,
            'error': f"La condición de IVA '{cliente.condicion_iva}' del cliente "
                     f"'{cliente.nombre_completo}' no es válida para ARCA (esperado: RI, MONO, EX o CF).",
        }

    # FactuPsyware factura servicios (soporte tecnico, abonos, consultas), no
    # productos. Concepto=2 (Servicios) es obligatorio en ese caso, y trae
    # consigo la obligacion de informar FchServDesde/FchServHasta/FchVtoPago.
    # Si la factura no tiene periodo cargado (caso raro), se usa la fecha de
    # hoy como aproximacion para no dejar el campo vacio (AFIP lo exige).
    concepto = 2

    fch_serv_desde = factura.periodo_desde.strftime('%Y%m%d') if factura.periodo_desde else hoy
    fch_serv_hasta = factura.periodo_hasta.strftime('%Y%m%d') if factura.periodo_hasta else hoy
    # ARCA (10036): FchVtoPago no puede ser anterior a CbteFch (hoy).
    fch_vto_pago = max(factura.fecha_vto_pago.strftime('%Y%m%d'), hoy) if factura.fecha_vto_pago else hoy

    detalle = {
        'Concepto': concepto,
        'DocTipo': doc_tipo,
        'DocNro': doc_nro,
        'CbteDesde': proximo_numero,
        'CbteHasta': proximo_numero,
        'CbteFch': hoy,
        'FchServDesde': fch_serv_desde,
        'FchServHasta': fch_serv_hasta,
        'FchVtoPago': fch_vto_pago,
        'ImpTotal': imp_total,
        'ImpTotConc': 0,
        'ImpNeto': imp_neto,
        'ImpOpEx': 0,
        'ImpTrib': 0,
        'ImpIVA': imp_iva,
        'MonId': 'PES',
        'MonCotiz': 1,
        'CondicionIVAReceptorId': condicion_iva_receptor,
        'Iva': {'AlicIva': iva_array},
    }

    # 5. Si es Nota de Crédito/Débito asociada a un comprobante, agregar CbtesAsoc
    if factura.factura_asociada and (factura.es_nota_credito or factura.es_nota_debito):
        asociada = factura.factura_asociada
        if not asociada.numero:
            return {
                'ok': False,
                'error': f'El comprobante asociado (id={asociada.id}) no tiene número de ARCA asignado todavía.',
            }
        detalle['CbtesAsoc'] = {
            'CbteAsoc': [
                {
                    'Tipo': int(asociada.tipo_comprobante),
                    'PtoVta': asociada.punto_venta,
                    'Nro': asociada.numero,
                }
            ]
        }

    fe_cab_req = {
        'CantReg': 1,
        'PtoVta': factura.punto_venta,
        'CbteTipo': int(factura.tipo_comprobante),
    }

    logger.debug("FECAESolicitar entorno=%s PtoVta=%s CbteTipo=%s detalle=%s", datos['entorno'], factura.punto_venta, factura.tipo_comprobante, detalle)

    response = client.service.FECAESolicitar(
        Auth=auth,
        FeCAEReq={
            'FeCabReq': fe_cab_req,
            'FeDetReq': {'FECAEDetRequest': [detalle]},
        }
    )

    logger.debug("FECAESolicitar respuesta cruda entorno=%s: %s", datos['entorno'], response)

    # Errores a nivel de respuesta global (cabecera): problemas de
    # autenticacion, formato del request, autorizacion del servicio, etc.
    # Si vienen por aca, el detalle del comprobante puede no traer
    # Observaciones, y por eso antes se mostraba "Rechazado sin detalle".
    errores_generales = []
    if getattr(response, 'Errors', None):
        for e in response.Errors.Err:
            errores_generales.append(str(e.Code) + ': ' + str(e.Msg))

    if errores_generales:
        return {
            'ok': False,
            'error': '; '.join(errores_generales),
        }

    resultado = response.FeDetResp.FECAEDetResponse[0]

    if resultado.Resultado == 'A':
        return {
            'ok': True,
            'numero': proximo_numero,
            'cae': resultado.CAE,
            'cae_vencimiento': resultado.CAEFchVto,
        }
    else:
        observaciones = resultado.Observaciones.Obs if resultado.Observaciones else []
        errores = '; '.join(str(o.Code) + ': ' + str(o.Msg) for o in observaciones)
        if not errores:
            errores = 'Rechazado sin detalle. Respuesta cruda: ' + str(response)
        return {
            'ok': False,
            'error': errores,
        }
