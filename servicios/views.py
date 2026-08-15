from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
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