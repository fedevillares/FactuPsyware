from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db import models

from clientes.models import Cliente
from .models import Ticket, TicketEvento
from .emailing import asunto_ticket, cuerpo_sugerido, enviar_notificacion_ticket


@login_required
def listado_tickets(request):
    tickets = Ticket.objects.select_related('cliente').all()

    q = request.GET.get('q', '').strip()
    if q:
        tickets = tickets.filter(
            models.Q(titulo__icontains=q) |
            models.Q(cliente__nombre_completo__icontains=q)
        )

    estado = request.GET.get('estado', '').strip()
    if estado in dict(Ticket.ESTADOS):
        tickets = tickets.filter(estado=estado)

    return render(request, 'tickets/listado.html', {
        'tickets': tickets,
        'q': q,
        'estado': estado,
    })


@login_required
def nuevo_ticket(request):
    clientes = Cliente.objects.order_by('nombre_completo')

    if request.method == 'POST':
        cliente_id = request.POST.get('cliente')
        titulo = request.POST.get('titulo', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        contacto_nombre = request.POST.get('contacto_nombre', '').strip()
        contacto_email = request.POST.get('contacto_email', '').strip()

        error = None
        cliente = None
        try:
            cliente = Cliente.objects.get(id=cliente_id)
        except (Cliente.DoesNotExist, ValueError, TypeError):
            error = "Elegí una empresa/cliente para el ticket."

        if not error and not titulo:
            error = "El ticket necesita un título."
        if not error and not descripcion:
            error = "El ticket necesita una descripción."

        if error:
            return render(request, 'tickets/nuevo.html', {
                'clientes': clientes, 'error': error,
                'titulo': titulo, 'descripcion': descripcion,
                'contacto_nombre': contacto_nombre, 'contacto_email': contacto_email,
                'cliente_id': cliente_id,
            })

        # Si no se completó el contacto a mano, se toma el de soporte del cliente.
        if not contacto_nombre:
            contacto_nombre = cliente.contacto_soporte_nombre or ''
        if not contacto_email:
            contacto_email = cliente.contacto_soporte_email or ''

        ticket = Ticket.objects.create(
            cliente=cliente,
            titulo=titulo,
            descripcion=descripcion,
            contacto_nombre=contacto_nombre,
            contacto_email=contacto_email,
        )
        # Tras crear, se pasa a la pantalla de notificación de apertura.
        return redirect(f"{_url_notificar(ticket)}?tipo=apertura")

    return render(request, 'tickets/nuevo.html', {'clientes': clientes})


@login_required
def detalle_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket.objects.select_related('cliente'), id=ticket_id)
    return render(request, 'tickets/detalle.html', {'ticket': ticket})


@login_required
@require_POST
def cerrar_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)
    nota = request.POST.get('nota', '').strip()
    if ticket.estado != 'CERRADO':
        ticket.estado = 'CERRADO'
        ticket.fecha_fin = timezone.now()
        ticket.save(update_fields=['estado', 'fecha_fin'])
        TicketEvento.objects.create(ticket=ticket, tipo='CIERRE', nota=nota)
    return redirect(f"{_url_notificar(ticket)}?tipo=cierre")


@login_required
@require_POST
def reabrir_ticket(request, ticket_id):
    ticket = get_object_or_404(Ticket, id=ticket_id)
    nota = request.POST.get('nota', '').strip()
    if ticket.estado != 'PENDIENTE':
        ticket.estado = 'PENDIENTE'
        ticket.fecha_fin = None
        ticket.save(update_fields=['estado', 'fecha_fin'])
        TicketEvento.objects.create(ticket=ticket, tipo='REAPERTURA', nota=nota)
    return redirect(f"{_url_notificar(ticket)}?tipo=reapertura")


@login_required
def notificar_ticket(request, ticket_id):
    """Pantalla de revisión/envío del email de apertura o cierre.
    Se sugiere el texto automáticamente pero es editable antes de enviar."""
    ticket = get_object_or_404(Ticket.objects.select_related('cliente'), id=ticket_id)

    if request.method == 'POST':
        destinatario = request.POST.get('destinatario', '').strip()
        asunto = request.POST.get('asunto', '').strip() or asunto_ticket(ticket)
        cuerpo = request.POST.get('cuerpo', '').strip()

        if not destinatario:
            return render(request, 'tickets/notificar.html', {
                'ticket': ticket, 'destinatario': destinatario,
                'asunto': asunto, 'cuerpo': cuerpo,
                'mensaje': 'Ingresá un email de destino (contacto de soporte del cliente).',
                'exito': False,
            })

        exito, mensaje = enviar_notificacion_ticket(destinatario, asunto, cuerpo)
        if exito:
            return redirect('detalle_ticket', ticket_id=ticket.id)

        return render(request, 'tickets/notificar.html', {
            'ticket': ticket, 'destinatario': destinatario,
            'asunto': asunto, 'cuerpo': cuerpo,
            'mensaje': mensaje, 'exito': False,
        })

    tipo = request.GET.get('tipo', 'apertura')
    if tipo not in ('apertura', 'cierre', 'reapertura'):
        tipo = 'apertura'

    return render(request, 'tickets/notificar.html', {
        'ticket': ticket,
        'tipo': tipo,
        'destinatario': ticket.contacto_email or ticket.cliente.contacto_soporte_email or '',
        'asunto': asunto_ticket(ticket),
        'cuerpo': cuerpo_sugerido(ticket, tipo),
    })


def _url_notificar(ticket):
    from django.urls import reverse
    return reverse('notificar_ticket', args=[ticket.id])
