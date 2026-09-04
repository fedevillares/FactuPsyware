from django.contrib import admin
from django.contrib import messages
from decimal import Decimal
from django.shortcuts import render
from .models import Servicio


def aplicar_aumento(modeladmin, request, queryset):
    if 'apply' in request.POST:
        porcentaje = Decimal(request.POST.get('porcentaje', '0'))
        for servicio in queryset:
            nuevo_precio = servicio.precio_unitario * (1 + porcentaje / 100)
            servicio.precio_unitario = round(nuevo_precio, 2)
            servicio.save()
        modeladmin.message_user(
            request,
            f'Se actualizaron {queryset.count()} servicios con un {porcentaje}% de aumento.',
            messages.SUCCESS
        )
        return None

    return render(request, 'admin/aplicar_aumento.html', {
        'servicios': queryset,
        'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
    })


aplicar_aumento.short_description = 'Aplicar %% de aumento por inflacion a los seleccionados'


@admin.register(Servicio)
class ServicioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio_unitario', 'alicuota_iva', 'precio_con_iva', 'activo')
    list_display_links = ('nombre',)
    search_fields = ('nombre',)
    list_filter = ('activo', 'alicuota_iva')
    list_editable = ('precio_unitario', 'activo')
    ordering = ('nombre',)
    list_per_page = 50
    actions = [aplicar_aumento]