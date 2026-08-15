from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Factura, FacturaItem
from arca.services import emitir_factura
from arca.qr import generar_qr_base64
from arca.models import EmpresaConfig


@login_required
def listado_facturas(request):
    facturas = Factura.objects.all().order_by('-id')
    return render(request, 'facturas/listado.html', {'facturas': facturas})


@login_required
def detalle_factura(request, factura_id):
    factura = get_object_or_404(Factura, id=factura_id)
    return render(request, 'facturas/detalle.html', {'factura': factura})


@login_required
def emitir(request, factura_id):
    factura = get_object_or_404(Factura, id=factura_id)
    if request.method == 'POST':
        exito, mensaje = emitir_factura(factura)
        return render(request, 'facturas/detalle.html', {'factura': factura, 'mensaje': mensaje, 'exito': exito})
    return redirect('detalle_factura', factura_id=factura.id)


@login_required
def comprobante(request, factura_id):
    factura = get_object_or_404(Factura, id=factura_id)

    if not factura.cae:
        return redirect('detalle_factura', factura_id=factura.id)

    qr_b64 = generar_qr_base64(factura)
    empresa = EmpresaConfig.get_config()
    otros_impuestos = round(float(factura.total) * float(empresa.otros_impuestos_pct) / 100, 2)
    return render(request, 'facturas/comprobante.html', {
        'factura': factura,
        'qr_b64': qr_b64,
        'empresa': empresa,
        'otros_impuestos': otros_impuestos,
    })


@login_required
def comprobante_preview(request, factura_id):
    """Vista previa del comprobante para una factura que todavia no tiene
    CAE (BORRADOR o ERROR). No genera QR real (no hay CAE/numero validos
    todavia) ni toca nada de ARCA: sirve solo para revisar el diseno del
    PDF antes de emitir. No reemplaza ni se confunde con `comprobante`,
    que es la vista oficial post-CAE."""
    factura = get_object_or_404(Factura, id=factura_id)
    empresa = EmpresaConfig.get_config()
    otros_impuestos = round(float(factura.total) * float(empresa.otros_impuestos_pct) / 100, 2)
    return render(request, 'facturas/comprobante.html', {
        'factura': factura,
        'qr_b64': None,
        'empresa': empresa,
        'otros_impuestos': otros_impuestos,
        'es_preview': True,
    })


MAPA_NOTA_CREDITO = {'1': '3', '6': '8', '11': '13'}
MAPA_NOTA_DEBITO = {'1': '2', '6': '7', '11': '12'}


@login_required
def generar_nota(request, factura_id, tipo_nota):
    factura = get_object_or_404(Factura, id=factura_id)

    if not factura.cae:
        return redirect('detalle_factura', factura_id=factura.id)

    mapa = MAPA_NOTA_CREDITO if tipo_nota == 'credito' else MAPA_NOTA_DEBITO
    nuevo_tipo = mapa.get(factura.tipo_comprobante)

    if not nuevo_tipo:
        return redirect('detalle_factura', factura_id=factura.id)

    # Se copian periodo_desde/hasta y fecha_vto_pago de la factura original:
    # ARCA exige informar el periodo de servicio (FchServDesde/Hasta/FchVtoPago)
    # tambien en la Nota de Credito/Debito, y debe corresponder al comprobante
    # que se esta corrigiendo, no a la fecha de hoy.
    nueva = Factura.objects.create(
        cliente=factura.cliente,
        tipo_comprobante=nuevo_tipo,
        punto_venta=factura.punto_venta,
        factura_asociada=factura,
        condicion_venta=factura.condicion_venta,
        periodo_desde=factura.periodo_desde,
        periodo_hasta=factura.periodo_hasta,
        fecha_vto_pago=factura.fecha_vto_pago,
    )

    for item in factura.items.all():
        FacturaItem.objects.create(
            factura=nueva,
            servicio=item.servicio,
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            alicuota_iva=item.alicuota_iva,
        )

    return redirect('detalle_factura', factura_id=nueva.id)


@login_required
def eliminar_factura(request, factura_id):
    factura = get_object_or_404(Factura, id=factura_id)

    if factura.estado == 'AUTORIZADA':
        return redirect('detalle_factura', factura_id=factura.id)

    if request.method == 'POST':
        factura.delete()
        return redirect('listado_facturas')

    return redirect('detalle_factura', factura_id=factura.id)
