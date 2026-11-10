import io
import zipfile
import datetime
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import ProtectedError
from django.conf import settings
from django.utils import timezone
from .models import Factura, FacturaItem
from . import cotizaciones
from .moneda import redondear_cotizacion
from clientes.models import Cliente
from servicios.models import Servicio
from arca.services import emitir_factura
from arca.qr import generar_qr_base64
from arca.models import EmpresaConfig

TIPOS_COMPROBANTE_NUEVA_FACTURA = [
    ('1', 'Factura A'), ('6', 'Factura B'), ('11', 'Factura C'),
]


def _facturas_filtradas_base(request):
    """Queryset filtrado por q/estado, sin select_related/prefetch: para
    conteos y métricas del encabezado que no necesitan cliente/items."""
    facturas = Factura.objects.order_by('-id')

    q = request.GET.get('q', '').strip()
    if q:
        facturas = facturas.filter(
            models.Q(cliente__nombre_completo__icontains=q) |
            models.Q(numero__icontains=q) |
            models.Q(cae__icontains=q)
        )

    estado = request.GET.get('estado', '').strip()
    if estado in dict(Factura.ESTADOS):
        facturas = facturas.filter(estado=estado)

    return facturas, q, estado


def _facturas_filtradas(request):
    facturas, q, estado = _facturas_filtradas_base(request)
    facturas = facturas.select_related('cliente').prefetch_related('items')
    return facturas, q, estado


@login_required
def listado_facturas(request):
    facturas_base, q, estado = _facturas_filtradas_base(request)

    # Métricas del encabezado: sobre el filtro completo de producción, no
    # sobre la página actual, y sin traer cliente/items (no hacen falta acá).
    metricas = list(
        facturas_base.exclude(entorno_emision='homologacion')
        .only('estado', 'pagada', 'fecha_vto_pago', 'fecha_emision', 'tipo_comprobante')
    )
    hoy = datetime.date.today()
    cantidad_mes = sum(
        1 for f in metricas
        if f.fecha_emision.year == hoy.year and f.fecha_emision.month == hoy.month
    )
    pendientes_cobro = sum(
        1 for f in metricas
        if f.estado == 'AUTORIZADA' and not f.es_nota_credito
        and not f.pagada and not f.esta_vencida
    )
    vencidas = sum(1 for f in metricas if f.esta_vencida)

    facturas_display, _, _ = _facturas_filtradas(request)
    facturas_produccion_qs = facturas_display.exclude(entorno_emision='homologacion')
    facturas_homologacion = list(facturas_display.filter(entorno_emision='homologacion'))

    paginador = Paginator(facturas_produccion_qs, 100)
    pagina_produccion = paginador.get_page(request.GET.get('page'))

    return render(request, 'facturas/listado.html', {
        'facturas_produccion': pagina_produccion,
        'pagina_produccion': pagina_produccion,
        'facturas_homologacion': facturas_homologacion,
        'q': q,
        'estado': estado,
        'hay_homologacion': len(facturas_homologacion) > 0,
        'cantidad_mes': cantidad_mes,
        'pendientes_cobro': pendientes_cobro,
        'vencidas': vencidas,
    })


def _datos_moneda_desde_post(request):
    """Lee moneda y cotización del formulario (nueva factura / actualizar
    cotización de un borrador) y resuelve qué se guarda en la factura.

    Devuelve (campos, error, pedir_confirmacion_desvio). `campos` son los
    valores de moneda/cotización listos para asignar al modelo.
      - Pesos: cotización 1, sin fuente.
      - Dólares, modo automático: el valor lo trae el servidor desde la API
        (no se confía en lo que mande el navegador).
      - Dólares, modo manual: el valor escrito queda como override; si se
        desvía más de COTIZACION_DESVIO_MAXIMO_PCT de la automática hay que
        confirmarlo explícitamente.
    """
    moneda = request.POST.get('moneda', '').strip() or 'ARS'
    if moneda not in dict(Factura.MONEDAS):
        return None, "Elegí una moneda válida.", False

    if moneda == 'ARS':
        return {
            'moneda': 'ARS', 'cotizacion': Decimal('1'), 'cotizacion_fuente': '',
            'cotizacion_fecha': None, 'cancela_misma_moneda': False,
        }, None, False

    campos = {
        'moneda': moneda,
        'cancela_misma_moneda': bool(request.POST.get('cancela_misma_moneda')),
    }

    if request.POST.get('cotizacion_modo', 'auto') == 'manual':
        try:
            cotizacion = redondear_cotizacion(
                Decimal(request.POST.get('cotizacion', '').strip().replace(',', '.'))
            )
        except (InvalidOperation, TypeError):
            return None, "Para facturar en dólares ingresá la cotización (pesos por 1 dólar).", False
        if cotizacion <= 0:
            return None, "La cotización tiene que ser mayor a 0.", False
        if cotizacion >= 10000:
            # ARCA admite hasta 4 enteros en MonCotiz.
            return None, "La cotización no puede tener más de 4 dígitos enteros.", False

        try:
            referencia = cotizaciones.get_rate()['valor']
        except cotizaciones.CotizacionNoDisponible:
            referencia = None
        if referencia and not request.POST.get('confirmar_desvio'):
            desvio = cotizaciones.desvio_porcentual(cotizacion, referencia)
            if desvio > Decimal(str(settings.COTIZACION_DESVIO_MAXIMO_PCT)):
                return None, (
                    f"La cotización manual ({cotizacion.normalize():f}) se desvía un {desvio:.1f}% de la "
                    f"automática ({referencia.normalize():f}). Si es correcta, marcá la casilla de "
                    f"confirmación y volvé a guardar."
                ), True

        campos.update({
            'cotizacion': cotizacion, 'cotizacion_fuente': 'manual',
            'cotizacion_fecha': timezone.now(),
        })
        return campos, None, False

    try:
        automatica = cotizaciones.get_rate()
    except cotizaciones.CotizacionNoDisponible:
        return None, (
            "No se pudo obtener la cotización automática del dólar. "
            "Elegí el modo Manual y cargala a mano."
        ), False
    campos.update({
        'cotizacion': automatica['valor'], 'cotizacion_fuente': automatica['fuente'],
        'cotizacion_fecha': automatica['fecha'],
    })
    return campos, None, False


def _contexto_nueva_factura(request, extra=None):
    contexto = {
        'clientes': Cliente.objects.order_by('nombre_completo'),
        'servicios': Servicio.objects.filter(activo=True).order_by('nombre'),
        'tipos_comprobante': TIPOS_COMPROBANTE_NUEVA_FACTURA,
        'condiciones_venta': Factura.CONDICIONES_VENTA,
        'alicuotas_iva': FacturaItem._meta.get_field('alicuota_iva').choices,
        'monedas': Factura.MONEDAS,
        'moneda': 'ARS',
        'cotizacion_modo': 'auto',
        'desvio_maximo_pct': settings.COTIZACION_DESVIO_MAXIMO_PCT,
    }
    if extra:
        contexto.update(extra)
    return contexto


@login_required
def nueva_factura(request):
    if request.method == 'POST':
        cliente_id = request.POST.get('cliente', '').strip()
        tipo_comprobante = request.POST.get('tipo_comprobante', '').strip()
        punto_venta = request.POST.get('punto_venta', '').strip()
        condicion_venta = request.POST.get('condicion_venta', '').strip()
        periodo_desde = request.POST.get('periodo_desde', '').strip()
        periodo_hasta = request.POST.get('periodo_hasta', '').strip()
        fecha_vto_pago = request.POST.get('fecha_vto_pago', '').strip()
        observaciones = request.POST.get('observaciones', '').strip()

        campos_repoblados = {
            'cliente_id': cliente_id, 'tipo_comprobante': tipo_comprobante,
            'punto_venta': punto_venta, 'condicion_venta': condicion_venta,
            'periodo_desde': periodo_desde, 'periodo_hasta': periodo_hasta,
            'fecha_vto_pago': fecha_vto_pago, 'observaciones': observaciones,
            'moneda': request.POST.get('moneda', '').strip() or 'ARS',
            'cotizacion_modo': request.POST.get('cotizacion_modo', 'auto'),
            'cotizacion': request.POST.get('cotizacion', '').strip(),
            'cancela_misma_moneda': bool(request.POST.get('cancela_misma_moneda')),
        }

        error = None
        cliente = None
        try:
            cliente = Cliente.objects.get(id=cliente_id)
        except (Cliente.DoesNotExist, ValueError, TypeError):
            error = "Elegí un cliente para la factura."

        if not error and tipo_comprobante not in dict(TIPOS_COMPROBANTE_NUEVA_FACTURA):
            error = "Elegí un tipo de comprobante válido."

        punto_venta_int = None
        if not error:
            try:
                punto_venta_int = int(punto_venta)
                if punto_venta_int <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                error = "Ingresá un punto de venta válido."

        if not error and condicion_venta not in dict(Factura.CONDICIONES_VENTA):
            error = "Elegí una condición de venta válida."

        items_data = []
        if not error:
            servicio_ids = request.POST.getlist('nuevo_servicio[]')
            descripciones = request.POST.getlist('nueva_descripcion[]')
            cantidades = request.POST.getlist('nueva_cantidad[]')
            precios = request.POST.getlist('nuevo_precio[]')
            alicuotas = request.POST.getlist('nueva_alicuota[]')
            alicuotas_validas = dict(FacturaItem._meta.get_field('alicuota_iva').choices)

            for i in range(len(cantidades)):
                servicio_id = servicio_ids[i] if i < len(servicio_ids) else ''
                descripcion = (descripciones[i] if i < len(descripciones) else '').strip()
                precio = precios[i] if i < len(precios) else ''
                alicuota = alicuotas[i] if i < len(alicuotas) else ''

                if not servicio_id and not descripcion:
                    continue

                servicio = None
                if servicio_id:
                    try:
                        servicio = Servicio.objects.get(id=servicio_id)
                    except (Servicio.DoesNotExist, ValueError):
                        error = "Uno de los productos elegidos no existe."
                        break

                try:
                    cantidad_dec = Decimal(cantidades[i])
                    precio_dec = Decimal(precio)
                except (InvalidOperation, TypeError, IndexError):
                    error = "Cantidad y precio deben ser números válidos en todos los ítems."
                    break

                if alicuota not in alicuotas_validas:
                    error = "Elegí una alícuota de IVA válida en todos los ítems."
                    break

                items_data.append({
                    'servicio': servicio,
                    'descripcion_personalizada': descripcion or None,
                    'cantidad': cantidad_dec,
                    'precio_unitario': precio_dec,
                    'alicuota_iva': alicuota,
                })

        if not error and not items_data:
            error = "Agregá al menos un ítem a la factura."

        campos_moneda = None
        if not error:
            campos_moneda, error, pedir_confirmacion_desvio = _datos_moneda_desde_post(request)
            campos_repoblados['pedir_confirmacion_desvio'] = pedir_confirmacion_desvio

        if error:
            return render(request, 'facturas/nueva.html', _contexto_nueva_factura(request, {
                'error': error, **campos_repoblados,
            }))

        with transaction.atomic():
            factura = Factura.objects.create(
                cliente=cliente,
                tipo_comprobante=tipo_comprobante,
                punto_venta=punto_venta_int,
                condicion_venta=condicion_venta,
                periodo_desde=periodo_desde or None,
                periodo_hasta=periodo_hasta or None,
                fecha_vto_pago=fecha_vto_pago or None,
                observaciones=observaciones or None,
                **campos_moneda,
            )
            for item in items_data:
                FacturaItem.objects.create(factura=factura, **item)

        return redirect('detalle_factura', factura_id=factura.id)

    empresa = EmpresaConfig.get_config()
    return render(request, 'facturas/nueva.html', _contexto_nueva_factura(request, {
        'punto_venta': empresa.punto_venta_defecto,
        'condicion_venta': 'TRANSFERENCIA',
        'tipo_comprobante': '6',
    }))


@login_required
def cotizacion_dolar(request):
    """Endpoint JSON para el formulario: cotización automática del dólar.
    `?forzar=1` saltea el cache (botón "Actualizar cotización"). Si no hay
    forma de obtenerla responde ok=false y el formulario pasa a carga manual."""
    try:
        cotizacion = cotizaciones.get_rate(forzar=bool(request.GET.get('forzar')))
    except cotizaciones.CotizacionNoDisponible as e:
        return JsonResponse({'ok': False, 'error': str(e)})
    return JsonResponse({
        'ok': True,
        'valor': f"{cotizacion['valor'].normalize():f}",
        'fuente': cotizacion['fuente'],
        'tipo': cotizacion['tipo'],
        'campo': cotizacion['campo'],
        'fecha': cotizacion['fecha'].isoformat(),
        'fecha_texto': timezone.localtime(cotizacion['fecha']).strftime('%d/%m/%Y %H:%M'),
        'desactualizada': cotizacion['desactualizada'],
    })


@login_required
def listado_facturas_firma(request):
    """Endpoint liviano para detectar cambios (propios o de otro dispositivo)
    sin recargar la página entera. Devuelve un valor que cambia si cambió
    algo dentro del mismo filtro que está viendo el usuario (nueva factura,
    CAE asignado, cobro actualizado, etc.)."""
    facturas, _, _ = _facturas_filtradas(request)
    agregado = facturas.aggregate(
        ultimo=models.Max('actualizado'), total=models.Count('id'),
    )
    ultimo = agregado['ultimo'].isoformat() if agregado['ultimo'] else ''
    firma = f"{agregado['total']}:{ultimo}"
    return JsonResponse({'firma': firma})


def _factura_optimizada(factura_id):
    """get_object_or_404 con select_related/prefetch: evita que cada
    @property de Factura (subtotal/total_iva/total/desglose_iva) dispare una
    query nueva por acceso a items, y que cada item dispare una query por
    servicio. Usar en toda vista que renderice detalle.html o genere un PDF."""
    return get_object_or_404(
        Factura.objects.select_related('cliente', 'factura_asociada')
        .prefetch_related('items__servicio'),
        id=factura_id,
    )


@login_required
def detalle_factura(request, factura_id):
    factura = _factura_optimizada(factura_id)
    return render(request, 'facturas/detalle.html', {'factura': factura})


@login_required
def emitir(request, factura_id):
    factura = _factura_optimizada(factura_id)
    if request.method == 'POST':
        entorno = request.POST.get('entorno')
        if entorno not in ('homologacion', 'produccion'):
            return render(request, 'facturas/detalle.html', {
                'factura': factura, 'exito': False,
                'mensaje': 'Elegí si esta autorización es de prueba o real antes de emitir.',
            })
        if entorno == 'produccion' and request.POST.get('confirmacion_real', '').strip().upper() != 'REAL':
            return render(request, 'facturas/detalle.html', {
                'factura': factura, 'exito': False,
                'mensaje': 'Para autorizar contra AFIP REAL tenés que escribir "REAL" en el campo de confirmación.',
            })
        exito, mensaje = emitir_factura(factura, entorno)
        return render(request, 'facturas/detalle.html', {
            'factura': factura, 'mensaje': mensaje, 'exito': exito
        })
    return redirect('detalle_factura', factura_id=factura.id)


@login_required
@require_POST
def actualizar_cobro(request, factura_id):
    """Guarda el seguimiento interno de cobro (pagada + fecha) y las retenciones.
    Solo aplica a comprobantes ya autorizados; no toca nada fiscal."""
    factura = _factura_optimizada(factura_id)
    if factura.estado != 'AUTORIZADA':
        return redirect('detalle_factura', factura_id=factura.id)

    pagada = bool(request.POST.get('pagada'))

    fecha_pago = None
    if pagada:
        fecha_str = request.POST.get('fecha_pago', '').strip()
        if fecha_str:
            try:
                fecha_pago = datetime.datetime.strptime(fecha_str, '%Y-%m-%d').date()
            except ValueError:
                return render(request, 'facturas/detalle.html', {
                    'factura': factura, 'exito': False,
                    'mensaje': 'La fecha de pago no es válida.',
                })
        else:
            return render(request, 'facturas/detalle.html', {
                'factura': factura, 'exito': False,
                'mensaje': 'Si marcás la factura como pagada, indicá la fecha de pago.',
            })

    def _retencion(nombre):
        valor = request.POST.get(nombre, '').strip() or '0'
        monto = Decimal(valor.replace(',', '.'))
        if monto < 0:
            raise InvalidOperation
        return monto

    try:
        retencion_iva = _retencion('retencion_iva')
        retencion_ganancias = _retencion('retencion_ganancias')
    except (InvalidOperation, TypeError):
        return render(request, 'facturas/detalle.html', {
            'factura': factura, 'exito': False,
            'mensaje': 'Revisá los montos de retención: tienen que ser números mayores o iguales a 0.',
        })

    factura.pagada = pagada
    factura.fecha_pago = fecha_pago
    factura.retencion_iva = retencion_iva
    factura.retencion_ganancias = retencion_ganancias
    factura.save(update_fields=['pagada', 'fecha_pago', 'retencion_iva', 'retencion_ganancias', 'actualizado'])

    return render(request, 'facturas/detalle.html', {
        'factura': factura, 'exito': True,
        'mensaje': 'Datos de cobro actualizados.',
    })


@login_required
@require_POST
def actualizar_cotizacion(request, factura_id):
    """Cambia la cotización de un comprobante en moneda extranjera que todavía
    no se emitió (borrador o rechazado). Una vez autorizado, la cotización
    queda fija: el comprobante es inmutable."""
    factura = _factura_optimizada(factura_id)
    if factura.estado not in ('BORRADOR', 'ERROR') or not factura.es_moneda_extranjera:
        return redirect('detalle_factura', factura_id=factura.id)

    datos_post = request.POST.copy()
    datos_post['moneda'] = factura.moneda
    request.POST = datos_post
    campos, error, pedir_confirmacion_desvio = _datos_moneda_desde_post(request)
    if error:
        return render(request, 'facturas/detalle.html', {
            'factura': factura, 'exito': False, 'mensaje': error,
            'pedir_confirmacion_desvio': pedir_confirmacion_desvio,
            'cotizacion_ingresada': request.POST.get('cotizacion', '').strip(),
        })

    for campo, valor in campos.items():
        setattr(factura, campo, valor)
    factura.save(update_fields=[*campos.keys(), 'actualizado'])

    return render(request, 'facturas/detalle.html', {
        'factura': factura, 'exito': True,
        'mensaje': 'Cotización actualizada.',
    })


@login_required
def comprobante(request, factura_id):
    """Comprobante oficial post-CAE: PDF igual al emitido por ARCA."""
    from arca.pdf_comprobante import generar_pdf
    factura = _factura_optimizada(factura_id)
    if not factura.cae:
        return redirect('detalle_factura', factura_id=factura.id)
    qr_b64 = generar_qr_base64(factura)
    empresa = EmpresaConfig.get_config()
    otros_impuestos = round(float(factura.total) * float(empresa.otros_impuestos_pct) / 100, 2)
    pdf_bytes = generar_pdf(
        factura=factura, empresa=empresa,
        otros_impuestos=otros_impuestos, qr_b64=qr_b64, es_preview=False
    )
    nombre = f"{factura.nombre_archivo}.pdf"
    resp = HttpResponse(pdf_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="{nombre}"'
    return resp


@login_required
def comprobante_preview(request, factura_id):
    """Vista previa en PDF para borradores/errores, sin CAE."""
    from arca.pdf_comprobante import generar_pdf
    factura = _factura_optimizada(factura_id)
    empresa = EmpresaConfig.get_config()
    otros_impuestos = round(float(factura.total) * float(empresa.otros_impuestos_pct) / 100, 2)
    pdf_bytes = generar_pdf(
        factura=factura, empresa=empresa,
        otros_impuestos=otros_impuestos, qr_b64=None, es_preview=True
    )
    nombre = f"preview_{factura.id}.pdf"
    resp = HttpResponse(pdf_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="{nombre}"'
    return resp


MAPA_NOTA_CREDITO = {'1': '3', '6': '8', '11': '13'}
MAPA_NOTA_DEBITO  = {'1': '2', '6': '7', '11': '12'}


@login_required
@require_POST
def generar_nota(request, factura_id, tipo_nota):
    factura = get_object_or_404(Factura, id=factura_id)

    if not factura.cae:
        return redirect('detalle_factura', factura_id=factura.id)

    mapa = MAPA_NOTA_CREDITO if tipo_nota == 'credito' else MAPA_NOTA_DEBITO
    nuevo_tipo = mapa.get(factura.tipo_comprobante)

    if not nuevo_tipo:
        return redirect('detalle_factura', factura_id=factura.id)

    nueva = Factura.objects.create(
        cliente=factura.cliente,
        tipo_comprobante=nuevo_tipo,
        punto_venta=factura.punto_venta,
        factura_asociada=factura,
        condicion_venta=factura.condicion_venta,
        periodo_desde=factura.periodo_desde,
        periodo_hasta=factura.periodo_hasta,
        # ARCA (10036) rechaza un vencimiento anterior a la fecha del comprobante,
        # y la nota se emite hoy: no heredar el vencimiento de la factura original.
        fecha_vto_pago=datetime.date.today(),
        # La nota se emite en la misma moneda y con la misma cotización que el
        # comprobante que ajusta (se puede cambiar desde el detalle del borrador).
        moneda=factura.moneda,
        cotizacion=factura.cotizacion,
        cotizacion_fuente=factura.cotizacion_fuente,
        cotizacion_fecha=factura.cotizacion_fecha,
        cancela_misma_moneda=factura.cancela_misma_moneda,
    )

    for item in factura.items.all():
        FacturaItem.objects.create(
            factura=nueva,
            servicio=item.servicio,
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            alicuota_iva=item.alicuota_iva,
            descripcion_personalizada=item.descripcion_personalizada,
        )

    return redirect('editar_nota', factura_id=nueva.id)


@login_required
def editar_nota(request, factura_id):
    factura = _factura_optimizada(factura_id)

    if not (factura.es_nota_credito or factura.es_nota_debito):
        return redirect('detalle_factura', factura_id=factura.id)
    if factura.estado not in ('BORRADOR', 'ERROR'):
        return redirect('detalle_factura', factura_id=factura.id)

    error = None
    alicuotas_validas = dict(FacturaItem._meta.get_field('alicuota_iva').choices)

    if request.method == 'POST':
        items_finales = []

        for item in factura.items.all():
            if request.POST.get(f'eliminar_{item.id}'):
                continue
            try:
                cantidad = Decimal(request.POST.get(f'cantidad_{item.id}', ''))
                precio_unitario = Decimal(request.POST.get(f'precio_unitario_{item.id}', ''))
                alicuota_iva = request.POST.get(f'alicuota_iva_{item.id}', '')
                if cantidad <= 0 or precio_unitario < 0 or alicuota_iva not in alicuotas_validas:
                    raise InvalidOperation
            except (InvalidOperation, TypeError):
                error = "Revisá los valores cargados, hay algún campo numérico inválido."
                break
            descripcion_personalizada = request.POST.get(f'descripcion_{item.id}', '').strip() or None
            items_finales.append({
                'item': item, 'cantidad': cantidad,
                'precio_unitario': precio_unitario, 'alicuota_iva': alicuota_iva,
                'descripcion_personalizada': descripcion_personalizada,
            })

        nuevos_servicio = request.POST.getlist('nuevo_servicio[]')
        nuevos_cantidad = request.POST.getlist('nueva_cantidad[]')
        nuevos_precio = request.POST.getlist('nuevo_precio[]')
        nuevos_alicuota = request.POST.getlist('nueva_alicuota[]')
        nuevos_descripcion = request.POST.getlist('nueva_descripcion[]')

        nuevas_lineas = []
        if not error:
            for servicio_id, cantidad, precio, alicuota, descripcion in zip(
                nuevos_servicio, nuevos_cantidad, nuevos_precio, nuevos_alicuota, nuevos_descripcion
            ):
                if not servicio_id:
                    continue
                try:
                    servicio = Servicio.objects.get(id=servicio_id)
                    cantidad = Decimal(cantidad)
                    precio = Decimal(precio)
                    if cantidad <= 0 or precio < 0 or alicuota not in alicuotas_validas:
                        raise InvalidOperation
                except Servicio.DoesNotExist:
                    error = "Uno de los productos agregados a mano ya no existe."
                    break
                except (InvalidOperation, TypeError):
                    error = "Revisá los valores del producto agregado a mano."
                    break
                nuevas_lineas.append({
                    'servicio': servicio, 'cantidad': cantidad,
                    'precio_unitario': precio, 'alicuota_iva': alicuota,
                    'descripcion_personalizada': descripcion.strip() or None,
                })

        if not error and not items_finales and not nuevas_lineas:
            error = "La nota necesita al menos un ítem."

        if not error:
            with transaction.atomic():
                ids_a_conservar = [linea['item'].id for linea in items_finales]
                factura.items.exclude(id__in=ids_a_conservar).delete()

                for linea in items_finales:
                    item = linea['item']
                    item.cantidad = linea['cantidad']
                    item.precio_unitario = linea['precio_unitario']
                    item.alicuota_iva = linea['alicuota_iva']
                    item.descripcion_personalizada = linea['descripcion_personalizada']
                    item.save()

                for linea in nuevas_lineas:
                    FacturaItem.objects.create(
                        factura=factura,
                        servicio=linea['servicio'],
                        cantidad=linea['cantidad'],
                        precio_unitario=linea['precio_unitario'],
                        alicuota_iva=linea['alicuota_iva'],
                        descripcion_personalizada=linea['descripcion_personalizada'],
                    )

            return redirect('detalle_factura', factura_id=factura.id)

    return render(request, 'facturas/editar_nota.html', {
        'factura': factura,
        'servicios': Servicio.objects.filter(activo=True).order_by('nombre'),
        'alicuotas_iva': FacturaItem._meta.get_field('alicuota_iva').choices,
        'error': error,
    })


@login_required
@require_POST
def eliminar_factura(request, factura_id):
    factura = get_object_or_404(Factura, id=factura_id)

    if factura.estado == 'AUTORIZADA' and factura.entorno_emision != 'homologacion':
        return redirect('detalle_factura', factura_id=factura.id)

    # Una factura EMITIENDO puede tener un CAE ya otorgado por ARCA que
    # todavía no se guardó localmente (emisión en curso o guardado fallido).
    # Borrarla destruiría el único rastro local de un comprobante fiscal:
    # primero hay que resolver su estado (ver logs/arca_emisiones.log).
    if factura.estado == 'EMITIENDO':
        return redirect('detalle_factura', factura_id=factura.id)

    try:
        factura.delete()
    except ProtectedError:
        # Tiene una Nota de Crédito/Débito asociada (factura_asociada la
        # protege). Hay que borrar esa nota primero.
        return redirect('detalle_factura', factura_id=factura.id)
    return redirect('listado_facturas')


@login_required
@require_POST
def eliminar_facturas_homologacion(request):
    """Borra en bloque todas las facturas de homologación (sin validez fiscal)."""
    Factura.objects.filter(entorno_emision='homologacion').delete()
    return redirect('listado_facturas')


@login_required
def reporte_mensual(request):
    hoy = datetime.date.today()
    try:
        anio = int(request.GET.get('anio', hoy.year))
    except ValueError:
        anio = hoy.year
    try:
        mes = int(request.GET.get('mes', hoy.month))
    except ValueError:
        mes = hoy.month
    if mes < 1 or mes > 12:
        mes = hoy.month

    facturas_mes = list(
        Factura.objects.filter(
            estado='AUTORIZADA', fecha_emision__year=anio, fecha_emision__month=mes
        )
        .select_related('cliente')
        .prefetch_related('items')
        .order_by('-fecha_emision', '-numero')
    )

    # Métricas separadas por moneda (nunca se suman pesos con dólares). Lo
    # único que mezcla monedas es `total_convertido_ars`, que convierte cada
    # comprobante con SU cotización guardada.
    cantidad_total = len(facturas_mes)
    cero = Decimal('0.00')
    por_moneda = {}
    total_convertido_ars = cero

    for f in facturas_mes:
        totales = f.totales
        # Para la tabla del reporte: evita recalcular en el template.
        f.total_reporte = totales['total']
        m = por_moneda.setdefault(f.moneda, {
            'moneda': f.moneda, 'simbolo': f.simbolo_moneda, 'nombre': f.get_moneda_display(),
            'cantidad': 0, 'cantidad_notas_credito': 0,
            'neto_facturado': cero, 'iva': cero, 'devuelto': cero,
            'neto_cobrado': cero, 'pendiente_cobro': cero,
            'retenciones': cero, 'total_ars': cero,
        })
        m['cantidad'] += 1
        # Las retenciones se cargan siempre en pesos, sea cual sea la moneda.
        m['retenciones'] += f.retencion_iva + f.retencion_ganancias
        if f.es_nota_credito:
            m['cantidad_notas_credito'] += 1
            m['neto_facturado'] -= totales['neto']
            m['iva'] -= totales['iva']
            m['devuelto'] += totales['total']
            m['total_ars'] -= totales['total_ars']
            total_convertido_ars -= totales['total_ars']
        else:
            m['neto_facturado'] += totales['neto']
            m['iva'] += totales['iva']
            m['total_ars'] += totales['total_ars']
            total_convertido_ars += totales['total_ars']
            if f.pagada:
                m['neto_cobrado'] += totales['neto']
            else:
                m['pendiente_cobro'] += totales['total']

    for m in por_moneda.values():
        m['total_general'] = m['neto_facturado'] + m['iva']
    # Pesos primero, después el resto.
    metricas_por_moneda = sorted(por_moneda.values(), key=lambda m: (m['moneda'] != 'ARS', m['moneda']))
    cantidad_notas_credito = sum(m['cantidad_notas_credito'] for m in metricas_por_moneda)

    anios_disponibles = sorted(set(
        Factura.objects.filter(estado='AUTORIZADA').values_list('fecha_emision__year', flat=True)
    ), reverse=True) or [hoy.year]

    meses = [
        (1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'),
        (5, 'Mayo'), (6, 'Junio'), (7, 'Julio'), (8, 'Agosto'),
        (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre'),
    ]

    return render(request, 'facturas/reporte.html', {
        'anio': anio, 'mes': mes,
        'anios_disponibles': anios_disponibles,
        'meses': meses,
        'cantidad_total': cantidad_total,
        'cantidad_notas_credito': cantidad_notas_credito,
        'metricas_por_moneda': metricas_por_moneda,
        'hay_moneda_extranjera': any(m['moneda'] != 'ARS' for m in metricas_por_moneda),
        'total_convertido_ars': total_convertido_ars,
        'facturas_mes': facturas_mes,
    })


def _facturas_desde_ids(request):
    ids = request.GET.getlist('ids') or request.POST.getlist('ids')
    ids = [i for i in ids if i.isdigit()]
    return (
        Factura.objects.filter(id__in=ids, estado='AUTORIZADA')
        .select_related('cliente', 'factura_asociada')
        .prefetch_related('items__servicio')
    )


@login_required
def preparar_envio(request):
    facturas = list(_facturas_desde_ids(request))
    if not facturas:
        return redirect('listado_facturas')

    destinatario = ''
    clientes_emails = {f.cliente.email for f in facturas if f.cliente.email}
    if len(clientes_emails) == 1:
        destinatario = clientes_emails.pop()

    if len(facturas) == 1:
        asunto = f"{facturas[0].get_tipo_comprobante_display()} N° {facturas[0].numero_completo}"
    else:
        asunto = f"Comprobantes ({len(facturas)})"

    return render(request, 'facturas/enviar.html', {
        'facturas': facturas,
        'ids': [f.id for f in facturas],
        'destinatario': destinatario,
        'asunto': asunto,
    })


@login_required
@require_POST
def enviar_facturas(request):
    from .emailing import enviar_facturas_por_email

    facturas = list(_facturas_desde_ids(request))
    if not facturas:
        return redirect('listado_facturas')

    destinatario = request.POST.get('destinatario', '').strip()
    asunto = request.POST.get('asunto', '').strip() or 'Comprobante'
    cuerpo = request.POST.get('cuerpo', '').strip()

    if not destinatario:
        return render(request, 'facturas/enviar.html', {
            'facturas': facturas, 'ids': [f.id for f in facturas],
            'destinatario': destinatario, 'asunto': asunto, 'cuerpo': cuerpo,
            'mensaje': 'Ingresá un email de destino.', 'exito': False,
        })

    exito, mensaje = enviar_facturas_por_email(facturas, destinatario, asunto, cuerpo)

    if exito:
        return redirect('listado_facturas')

    return render(request, 'facturas/enviar.html', {
        'facturas': facturas, 'ids': [f.id for f in facturas],
        'destinatario': destinatario, 'asunto': asunto, 'cuerpo': cuerpo,
        'mensaje': mensaje, 'exito': exito,
    })


@login_required
def descargar_zip(request):
    from arca.pdf_comprobante import generar_pdf

    facturas = list(_facturas_desde_ids(request))
    if not facturas:
        return redirect('listado_facturas')

    empresa = EmpresaConfig.get_config()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for factura in facturas:
            qr_b64 = generar_qr_base64(factura) if factura.cae else None
            otros_impuestos = round(float(factura.total) * float(empresa.otros_impuestos_pct) / 100, 2)
            pdf_bytes = generar_pdf(
                factura=factura, empresa=empresa,
                otros_impuestos=otros_impuestos, qr_b64=qr_b64, es_preview=not factura.cae,
            )
            nombre = f"{factura.nombre_archivo}.pdf"
            zf.writestr(nombre, pdf_bytes)

    buffer.seek(0)
    resp = HttpResponse(buffer.read(), content_type='application/zip')
    resp['Content-Disposition'] = 'attachment; filename="comprobantes.zip"'
    return resp
