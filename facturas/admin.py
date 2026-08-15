from django.contrib import admin
from .models import Factura, FacturaItem


class FacturaItemInline(admin.TabularInline):
    model = FacturaItem
    extra = 1

    class Media:
        js = ('js/factura_item_admin.js',)


@admin.register(Factura)
class FacturaAdmin(admin.ModelAdmin):
    list_display = ('id', 'tipo_comprobante', 'numero_completo', 'cliente', 'fecha_emision', 'estado', 'cae')
    list_filter = ('estado', 'tipo_comprobante')
    search_fields = ('cliente__nombre_completo', 'numero')
    fields = ('cliente', 'tipo_comprobante', 'factura_asociada', 'punto_venta', 'condicion_venta',
              'periodo_desde', 'periodo_hasta', 'fecha_vto_pago', 'observaciones')
    inlines = [FacturaItemInline]