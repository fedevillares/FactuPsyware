import datetime
from . import config


def get_client():
    return config.get_zeep_client(config.WSFE_URL)


def ultimo_comprobante(token, sign, punto_venta, tipo_cbte):
    """Consulta el último número de comprobante autorizado para un punto de venta y tipo."""
    client = get_client()

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


def solicitar_cae(token, sign, factura):
    """
    Solicita el CAE para una Factura (modelo de Django) ya con sus items cargados.
    Devuelve un diccionario con 'cae', 'cae_vencimiento', 'numero' si fue exitoso,
    o 'error' con el detalle si falló.
    """
    client = get_client()

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

    hoy = datetime.date.today().strftime('%Y%m%d')

    # 3. Determinar tipo y número de documento del cliente
    cliente = factura.cliente
    doc_tipo = int(cliente.tipo_documento)

    if doc_tipo == 99:
        doc_nro = 0
    else:
        doc_nro_str = cliente.numero_documento.replace('-', '').replace('.', '').strip()
        doc_nro = int(doc_nro_str) if doc_nro_str else 0

    # 4. Condición frente al IVA del receptor (requerido por RG 5616)
    CONDICION_IVA_ARCA = {
        'RI': 1,
        'MONO': 6,
        'EX': 4,
        'CF': 5,
    }
    condicion_iva_receptor = CONDICION_IVA_ARCA[cliente.condicion_iva]

    # FactuPsyware factura servicios (soporte tecnico, abonos, consultas), no
    # productos. Concepto=2 (Servicios) es obligatorio en ese caso, y trae
    # consigo la obligacion de informar FchServDesde/FchServHasta/FchVtoPago.
    # Si la factura no tiene periodo cargado (caso raro), se usa la fecha de
    # hoy como aproximacion para no dejar el campo vacio (AFIP lo exige).
    concepto = 2

    fch_serv_desde = factura.periodo_desde.strftime('%Y%m%d') if factura.periodo_desde else hoy
    fch_serv_hasta = factura.periodo_hasta.strftime('%Y%m%d') if factura.periodo_hasta else hoy
    fch_vto_pago = factura.fecha_vto_pago.strftime('%Y%m%d') if factura.fecha_vto_pago else hoy

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
        'ImpTotal': round(factura.total, 2),
        'ImpTotConc': 0,
        'ImpNeto': round(factura.subtotal, 2),
        'ImpOpEx': 0,
        'ImpTrib': 0,
        'ImpIVA': round(factura.total_iva, 2),
        'MonId': 'PES',
        'MonCotiz': 1,
        'CondicionIVAReceptorId': condicion_iva_receptor,
        'Iva': {'AlicIva': iva_array},
    }

    # 5. Si es Nota de Crédito/Débito asociada a un comprobante, agregar CbtesAsoc
    if factura.factura_asociada and (factura.es_nota_credito or factura.es_nota_debito):
        asociada = factura.factura_asociada
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

    response = client.service.FECAESolicitar(
        Auth=auth,
        FeCAEReq={
            'FeCabReq': fe_cab_req,
            'FeDetReq': {'FECAEDetRequest': [detalle]},
        }
    )

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
