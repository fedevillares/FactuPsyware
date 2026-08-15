from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from clientes.models import Cliente
from facturas.models import Factura
from tickets.models import Ticket

from .models import Actividad, Lead, NotaLead
from .recordatorios import enviar_recordatorios_vencidos


@login_required
def kanban_leads(request):
    columnas = [
        (clave, etiqueta, Lead.objects.filter(estado=clave).select_related('cliente'))
        for clave, etiqueta in Lead.ESTADOS
    ]
    return render(request, 'crm/kanban.html', {'columnas': columnas})


@login_required
def nuevo_lead(request):
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        email = request.POST.get('email', '').strip()
        origen = request.POST.get('origen', '').strip()
        proximo_contacto = request.POST.get('proximo_contacto', '').strip() or None

        if not nombre:
            return render(request, 'crm/nuevo_lead.html', {
                'error': "El lead necesita un nombre.",
                'nombre': nombre, 'telefono': telefono, 'email': email,
                'origen': origen, 'proximo_contacto': proximo_contacto or '',
                'origen_choices': Lead.ORIGENES,
            })
        if origen not in dict(Lead.ORIGENES):
            origen = 'OTRO'

        lead = Lead.objects.create(
            nombre=nombre, telefono=telefono, email=email,
            origen=origen, proximo_contacto=proximo_contacto,
        )
        return redirect('detalle_lead', lead_id=lead.id)

    return render(request, 'crm/nuevo_lead.html', {'origen_choices': Lead.ORIGENES})


@login_required
def detalle_lead(request, lead_id):
    lead = get_object_or_404(Lead.objects.select_related('cliente'), id=lead_id)
    return render(request, 'crm/detalle_lead.html', {'lead': lead})


@login_required
@require_POST
def agregar_nota_lead(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    texto = request.POST.get('texto', '').strip()
    if texto:
        NotaLead.objects.create(lead=lead, texto=texto)
    return redirect('detalle_lead', lead_id=lead.id)


@login_required
@require_POST
def actualizar_estado_lead(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    estado = request.POST.get('estado', '').strip()
    if estado not in dict(Lead.ESTADOS) or estado == 'GANADO':
        return HttpResponseBadRequest("Estado inválido.")
    lead.estado = estado
    lead.save(update_fields=['estado', 'actualizado'])
    return HttpResponse(status=204)


def _validar_datos_cliente(datos):
    if not datos['nombre_completo']:
        return "El cliente necesita un nombre o razón social."
    if datos['tipo_documento'] not in dict(Cliente.TIPO_DOCUMENTO):
        return "Elegí un tipo de documento válido."
    if not datos['numero_documento']:
        return "El cliente necesita un número de documento."
    if datos['condicion_iva'] not in dict(Cliente.CONDICION_IVA):
        return "Elegí una condición frente al IVA válida."
    if Cliente.objects.filter(numero_documento=datos['numero_documento']).exists():
        return f"Ya existe un cliente con el documento {datos['numero_documento']}."
    return None


@login_required
def convertir_lead(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    if lead.cliente_id:
        return redirect('ficha_cliente_crm', cliente_id=lead.cliente_id)

    if request.method == 'POST':
        datos = {
            'nombre_completo': request.POST.get('nombre_completo', '').strip(),
            'tipo_documento': request.POST.get('tipo_documento', '').strip(),
            'numero_documento': request.POST.get('numero_documento', '').strip(),
            'condicion_iva': request.POST.get('condicion_iva', '').strip(),
            'telefono': request.POST.get('telefono', '').strip(),
            'email': request.POST.get('email', '').strip(),
            'direccion': request.POST.get('direccion', '').strip(),
        }
        error = _validar_datos_cliente(datos)
        if error:
            return render(request, 'crm/convertir_lead.html', {
                'lead': lead, 'error': error, 'datos': datos,
                'tipo_documento_choices': Cliente.TIPO_DOCUMENTO,
                'condicion_iva_choices': Cliente.CONDICION_IVA,
            })

        cliente = Cliente.objects.create(**datos)
        lead.cliente = cliente
        lead.estado = 'GANADO'
        lead.save(update_fields=['cliente', 'estado', 'actualizado'])
        return redirect('ficha_cliente_crm', cliente_id=cliente.id)

    datos = {
        'nombre_completo': lead.nombre, 'tipo_documento': '96',
        'numero_documento': '', 'condicion_iva': 'CF',
        'telefono': lead.telefono, 'email': lead.email, 'direccion': '',
    }
    return render(request, 'crm/convertir_lead.html', {
        'lead': lead, 'datos': datos,
        'tipo_documento_choices': Cliente.TIPO_DOCUMENTO,
        'condicion_iva_choices': Cliente.CONDICION_IVA,
    })


@login_required
def ficha_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    facturas = Factura.objects.filter(cliente=cliente).order_by('-fecha_emision')
    tickets = Ticket.objects.filter(cliente=cliente).order_by('-fecha_inicio')

    eventos = [{'fecha': f.fecha_emision, 'tipo': 'factura', 'obj': f} for f in facturas]
    eventos += [{'fecha': t.fecha_inicio.date(), 'tipo': 'ticket', 'obj': t} for t in tickets]
    eventos.sort(key=lambda e: e['fecha'], reverse=True)

    lead = Lead.objects.filter(cliente=cliente).prefetch_related('notas').first()

    facturas_autorizadas = [f for f in facturas if f.estado == 'AUTORIZADA']
    total_facturado = sum(f.total for f in facturas_autorizadas)
    anio_actual = timezone.localdate().year
    facturas_este_anio_count = sum(1 for f in facturas_autorizadas if f.fecha_emision.year == anio_actual)
    tickets_abiertos_count = sum(1 for t in tickets if not t.esta_cerrado)
    ultima_factura_fecha = facturas[0].fecha_emision if facturas else None

    return render(request, 'crm/ficha_cliente.html', {
        'cliente': cliente, 'eventos': eventos, 'lead': lead,
        'total_facturado': total_facturado,
        'facturas_este_anio_count': facturas_este_anio_count,
        'tickets_abiertos_count': tickets_abiertos_count,
        'ultima_factura_fecha': ultima_factura_fecha,
    })


@login_required
def editar_lead(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        email = request.POST.get('email', '').strip()
        origen = request.POST.get('origen', '').strip()
        proximo_contacto = request.POST.get('proximo_contacto', '').strip() or None

        if not nombre:
            return render(request, 'crm/editar_lead.html', {
                'lead': lead,
                'error': "El lead necesita un nombre.",
                'datos': {
                    'nombre': nombre, 'telefono': telefono, 'email': email,
                    'origen': origen, 'proximo_contacto': proximo_contacto or '',
                },
                'origen_choices': Lead.ORIGENES,
            })
        if origen not in dict(Lead.ORIGENES):
            origen = 'OTRO'

        lead.nombre = nombre
        lead.telefono = telefono
        lead.email = email
        lead.origen = origen
        lead.proximo_contacto = proximo_contacto
        lead.save(update_fields=['nombre', 'telefono', 'email', 'origen', 'proximo_contacto', 'actualizado'])
        return redirect('detalle_lead', lead_id=lead.id)

    datos = {
        'nombre': lead.nombre, 'telefono': lead.telefono, 'email': lead.email,
        'origen': lead.origen,
        'proximo_contacto': lead.proximo_contacto.strftime('%Y-%m-%d') if lead.proximo_contacto else '',
    }
    return render(request, 'crm/editar_lead.html', {
        'lead': lead, 'datos': datos, 'origen_choices': Lead.ORIGENES,
    })


@login_required
@require_POST
def agregar_actividad_lead(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    tipo = request.POST.get('tipo', '').strip()
    titulo = request.POST.get('titulo', '').strip()
    fecha = request.POST.get('fecha', '').strip()
    hecha = request.POST.get('hecha') == 'on'

    if tipo not in dict(Actividad.TIPOS):
        tipo = 'NOTA'
    if titulo and fecha:
        Actividad.objects.create(lead=lead, tipo=tipo, titulo=titulo, fecha=fecha, hecha=hecha)
    return redirect('detalle_lead', lead_id=lead.id)


@login_required
@require_POST
def marcar_actividad_hecha(request, actividad_id):
    actividad = get_object_or_404(Actividad, id=actividad_id)
    actividad.hecha = True
    actividad.save(update_fields=['hecha'])
    return redirect('detalle_lead', lead_id=actividad.lead_id)


@login_required
def crm_dashboard(request):
    enviar_recordatorios_vencidos()

    hoy = timezone.localdate()
    leads_activos = Lead.objects.exclude(estado__in=['GANADO', 'PERDIDO'])
    ganados = Lead.objects.filter(estado='GANADO').count()
    perdidos = Lead.objects.filter(estado='PERDIDO').count()
    tasa_conversion = round(ganados / (ganados + perdidos) * 100, 1) if (ganados + perdidos) else 0

    actividades_vencidas = Actividad.objects.filter(
        hecha=False, fecha__lte=hoy,
    ).select_related('lead').order_by('fecha')
    contactos_vencidos = leads_activos.filter(
        proximo_contacto__lte=hoy,
    ).order_by('proximo_contacto')

    facturas_autorizadas = Factura.objects.filter(
        estado='AUTORIZADA',
    ).select_related('cliente').prefetch_related('items')
    totales_por_cliente = {}
    for factura in facturas_autorizadas:
        totales_por_cliente.setdefault(factura.cliente, 0)
        totales_por_cliente[factura.cliente] += factura.total
    top_clientes = sorted(totales_por_cliente.items(), key=lambda kv: kv[1], reverse=True)[:10]

    return render(request, 'crm/dashboard.html', {
        'leads_activos_count': leads_activos.count(),
        'leads_activos': leads_activos.order_by('-creado')[:10],
        'tasa_conversion': tasa_conversion,
        'actividades_vencidas': actividades_vencidas,
        'contactos_vencidos': contactos_vencidos,
        'top_clientes': top_clientes,
    })
