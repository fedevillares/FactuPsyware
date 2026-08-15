from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Lead


@login_required
def kanban_leads(request):
    columnas = [
        (clave, etiqueta, Lead.objects.filter(estado=clave).select_related('cliente'))
        for clave, etiqueta in Lead.ESTADOS
    ]
    return render(request, 'crm/kanban.html', {'columnas': columnas})
