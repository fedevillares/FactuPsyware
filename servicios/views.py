from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db import models
from django.db.models import ProtectedError

from .models import Servicio


@login_required
def datos_servicio(request, servicio_id):
    try:
        servicio = Servicio.objects.get(id=servicio_id)
        return JsonResponse({
            'precio_unitario': str(servicio.precio_unitario),
            'alicuota_iva': servicio.alicuota_iva,
        })
    except Servicio.DoesNotExist:
        return JsonResponse({'error': 'No encontrado'}, status=404)


@login_required
def listado_servicios(request):
    servicios = Servicio.objects.all()

    q = request.GET.get('q', '').strip()
    if q:
        servicios = servicios.filter(models.Q(nombre__icontains=q))

    activo = request.GET.get('activo', '').strip()
    if activo == '1':
        servicios = servicios.filter(activo=True)
    elif activo == '0':
        servicios = servicios.filter(activo=False)

    servicios = servicios.order_by('nombre')

    return render(request, 'servicios/listado.html', {
        'servicios': servicios,
        'q': q,
        'activo': activo,
    })


def _render_form(request, contexto):
    contexto.setdefault('alicuota_choices', Servicio.ALICUOTAS_IVA)
    return render(request, 'servicios/form.html', contexto)


def _datos_form(request):
    return {
        'nombre': request.POST.get('nombre', '').strip(),
        'descripcion': request.POST.get('descripcion', '').strip(),
        'precio_unitario': request.POST.get('precio_unitario', '').strip(),
        'alicuota_iva': request.POST.get('alicuota_iva', '').strip(),
        'activo': request.POST.get('activo') == 'on',
    }


def _validar(datos):
    if not datos['nombre']:
        return "El servicio necesita un nombre."
    try:
        precio = Decimal(datos['precio_unitario'])
        if precio < 0:
            return "El precio no puede ser negativo."
    except (InvalidOperation, TypeError):
        return "Ingresá un precio válido."
    if datos['alicuota_iva'] not in dict(Servicio.ALICUOTAS_IVA):
        return "Elegí una alícuota de IVA válida."
    return None


@login_required
def nuevo_servicio(request):
    if request.method == 'POST':
        datos = _datos_form(request)
        error = _validar(datos)
        if error:
            return _render_form(request, {'error': error, 'datos': datos, 'es_nuevo': True})

        Servicio.objects.create(**datos)
        return redirect('listado_servicios')

    datos_iniciales = {'alicuota_iva': '5', 'activo': True}
    return _render_form(request, {'datos': datos_iniciales, 'es_nuevo': True})


@login_required
def editar_servicio(request, servicio_id):
    servicio = get_object_or_404(Servicio, id=servicio_id)

    if request.method == 'POST':
        datos = _datos_form(request)
        error = _validar(datos)
        if error:
            return _render_form(request, {
                'error': error, 'datos': datos, 'es_nuevo': False, 'servicio': servicio,
            })

        for campo, valor in datos.items():
            setattr(servicio, campo, valor)
        servicio.save()
        return redirect('listado_servicios')

    datos = {
        'nombre': servicio.nombre,
        'descripcion': servicio.descripcion or '',
        'precio_unitario': servicio.precio_unitario,
        'alicuota_iva': servicio.alicuota_iva,
        'activo': servicio.activo,
    }
    return _render_form(request, {'datos': datos, 'es_nuevo': False, 'servicio': servicio})


@login_required
@require_POST
def eliminar_servicio(request, servicio_id):
    servicio = get_object_or_404(Servicio, id=servicio_id)
    try:
        servicio.delete()
    except ProtectedError:
        servicio.activo = False
        servicio.save(update_fields=['activo'])
        servicios = Servicio.objects.order_by('nombre')
        return render(request, 'servicios/listado.html', {
            'servicios': servicios, 'q': '', 'activo': '',
            'error': (
                f"No se puede eliminar \"{servicio.nombre}\": tiene facturas asociadas. "
                f"Se lo desactivó en su lugar (no va a aparecer al facturar)."
            ),
        })
    return redirect('listado_servicios')


@login_required
@require_POST
def alternar_activo(request, servicio_id):
    servicio = get_object_or_404(Servicio, id=servicio_id)
    servicio.activo = not servicio.activo
    servicio.save(update_fields=['activo'])
    return redirect('listado_servicios')


@login_required
def aplicar_aumento(request):
    ids = request.POST.getlist('ids') or request.GET.getlist('ids')
    servicios = Servicio.objects.filter(id__in=ids).order_by('nombre')

    if not servicios.exists():
        return redirect('listado_servicios')

    if request.method == 'POST' and 'porcentaje' in request.POST:
        try:
            porcentaje = Decimal(request.POST.get('porcentaje', '0'))
        except InvalidOperation:
            return render(request, 'servicios/aumento.html', {
                'servicios': servicios, 'ids': ids,
                'error': "Ingresá un porcentaje válido.",
            })
        for servicio in servicios:
            servicio.precio_unitario = round(servicio.precio_unitario * (1 + porcentaje / 100), 2)
            servicio.save(update_fields=['precio_unitario'])
        return redirect('listado_servicios')

    return render(request, 'servicios/aumento.html', {'servicios': servicios, 'ids': ids})
