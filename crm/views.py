from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Lead, NotaLead


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
