from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from .diagnostico import verificar_todos


@login_required
def panel_verificacion(request):
    resultados = verificar_todos()
    return render(request, 'arca/verificacion.html', {
        'homologacion': resultados['homologacion'],
        'produccion': resultados['produccion'],
    })
