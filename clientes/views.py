from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db import models
from django.db.models import ProtectedError, Count

from .models import Cliente


def _clientes_anotados():
    return Cliente.objects.annotate(
        num_facturas=Count('facturas', distinct=True),
        num_tickets=Count('tickets', distinct=True),
    )


@login_required
def listado_clientes(request):
    clientes = _clientes_anotados()

    q = request.GET.get('q', '').strip()
    if q:
        clientes = clientes.filter(
            models.Q(nombre_completo__icontains=q) |
            models.Q(numero_documento__icontains=q) |
            models.Q(email__icontains=q)
        )

    condicion_iva = request.GET.get('condicion_iva', '').strip()
    if condicion_iva in dict(Cliente.CONDICION_IVA):
        clientes = clientes.filter(condicion_iva=condicion_iva)

    clientes = clientes.order_by('nombre_completo')

    return render(request, 'clientes/listado.html', {
        'clientes': clientes,
        'q': q,
        'condicion_iva': condicion_iva,
    })


def _datos_form(request):
    return {
        'nombre_completo': request.POST.get('nombre_completo', '').strip(),
        'tipo_documento': request.POST.get('tipo_documento', '').strip(),
        'numero_documento': request.POST.get('numero_documento', '').strip(),
        'condicion_iva': request.POST.get('condicion_iva', '').strip(),
        'telefono': request.POST.get('telefono', '').strip(),
        'email': request.POST.get('email', '').strip(),
        'direccion': request.POST.get('direccion', '').strip(),
        'contacto_soporte_nombre': request.POST.get('contacto_soporte_nombre', '').strip(),
        'contacto_soporte_email': request.POST.get('contacto_soporte_email', '').strip(),
    }


def _render_form(request, contexto):
    contexto.setdefault('tipo_documento_choices', Cliente.TIPO_DOCUMENTO)
    contexto.setdefault('condicion_iva_choices', Cliente.CONDICION_IVA)
    return render(request, 'clientes/form.html', contexto)


def _validar(datos, cliente_actual=None):
    if not datos['nombre_completo']:
        return "El cliente necesita un nombre o razón social."
    if datos['tipo_documento'] not in dict(Cliente.TIPO_DOCUMENTO):
        return "Elegí un tipo de documento válido."
    if not datos['numero_documento']:
        return "El cliente necesita un número de documento."
    if datos['condicion_iva'] not in dict(Cliente.CONDICION_IVA):
        return "Elegí una condición frente al IVA válida."
    duplicado = Cliente.objects.filter(numero_documento=datos['numero_documento'])
    if cliente_actual:
        duplicado = duplicado.exclude(pk=cliente_actual.pk)
    if duplicado.exists():
        return f"Ya existe un cliente con el documento {datos['numero_documento']}."
    return None


@login_required
def nuevo_cliente(request):
    if request.method == 'POST':
        datos = _datos_form(request)
        error = _validar(datos)
        if error:
            return _render_form(request, {'error': error, 'datos': datos, 'es_nuevo': True})

        Cliente.objects.create(**datos)
        return redirect('listado_clientes')

    datos_iniciales = {'tipo_documento': '96', 'condicion_iva': 'CF'}
    return _render_form(request, {'datos': datos_iniciales, 'es_nuevo': True})


@login_required
def editar_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)

    if request.method == 'POST':
        datos = _datos_form(request)
        error = _validar(datos, cliente_actual=cliente)
        if error:
            return _render_form(request, {
                'error': error, 'datos': datos, 'es_nuevo': False, 'cliente': cliente,
            })

        for campo, valor in datos.items():
            setattr(cliente, campo, valor)
        cliente.save()
        return redirect('listado_clientes')

    datos = {
        'nombre_completo': cliente.nombre_completo,
        'tipo_documento': cliente.tipo_documento,
        'numero_documento': cliente.numero_documento,
        'condicion_iva': cliente.condicion_iva,
        'telefono': cliente.telefono or '',
        'email': cliente.email or '',
        'direccion': cliente.direccion or '',
        'contacto_soporte_nombre': cliente.contacto_soporte_nombre or '',
        'contacto_soporte_email': cliente.contacto_soporte_email or '',
    }
    return _render_form(request, {'datos': datos, 'es_nuevo': False, 'cliente': cliente})


@login_required
@require_POST
def eliminar_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    try:
        cliente.delete()
    except ProtectedError:
        clientes = _clientes_anotados().order_by('nombre_completo')
        return render(request, 'clientes/listado.html', {
            'clientes': clientes, 'q': '', 'condicion_iva': '',
            'error': f"No se puede eliminar a {cliente.nombre_completo}: tiene facturas o tickets asociados.",
        })
    return redirect('listado_clientes')
