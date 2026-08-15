from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Factura, FacturaItem
from arca.models import EmpresaConfig


class FacturaItemInline(admin.TabularInline):
    model = FacturaItem
    extra = 1

    class Media:
        js = ('js/factura_item_admin.js',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'servicio':
            kwargs['empty_label'] = "— Producto personalizado (sin catálogo) —"
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Factura)
class FacturaAdmin(admin.ModelAdmin):
    list_display = ('numero_completo', 'cliente', 'fecha_emision', 'estado_badge', 'total_display', 'cae')
    list_display_links = ('numero_completo',)
    list_filter = ('estado', 'tipo_comprobante')
    search_fields = ('cliente__nombre_completo', 'numero', 'cae')
    date_hierarchy = 'fecha_emision'
    list_select_related = ('cliente',)
    autocomplete_fields = ('cliente', 'factura_asociada')
    ordering = ('-id',)
    list_per_page = 50

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('items')

    fieldsets = (
        ('Comprobante', {
            'fields': ('cliente', 'tipo_comprobante', 'punto_venta', 'factura_asociada'),
        }),
        ('Condiciones de venta', {
            'fields': ('condicion_venta', 'periodo_desde', 'periodo_hasta', 'fecha_vto_pago'),
        }),
        ('Notas', {
            'fields': ('observaciones',),
            'classes': ('collapse',),
        }),
        ('Rechazo de ARCA', {
            'fields': ('error_arca',),
            'classes': ('collapse',),
        }),
        ('Recuperación manual de emisión', {
            'fields': ('estado', 'numero', 'cae', 'cae_vencimiento', 'entorno_emision'),
            'classes': ('collapse',),
            'description': (
                'Usar solo si una factura quedó trabada en "Emitiendo" tras un error de guardado '
                'posterior a que ARCA ya otorgó el CAE (ver logs/arca_emisiones.log). Completar '
                'estos campos a mano con los datos del log, o volver el estado a "Borrador" para '
                'poder reintentar la emisión.'
            ),
        }),
    )
    inlines = [FacturaItemInline]

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault('punto_venta', EmpresaConfig.get_config().punto_venta_defecto)
        return initial

    @admin.display(description='Estado', ordering='estado')
    def estado_badge(self, obj):
        clase = {
            'AUTORIZADA': 'stamp-autorizada',
            'ERROR': 'stamp-error',
        }.get(obj.estado, 'stamp-borrador')
        return format_html(
            '<span class="stamp {}" style="padding:4px 10px; font-size:11px;">{}</span>',
            clase, obj.get_estado_display(),
        )

    @admin.display(description='Total', ordering='id')
    def total_display(self, obj):
        return format_html('<span style="font-family:var(--font-mono);">$ {}</span>', f'{obj.total:.2f}')

    def response_add(self, request, obj, post_url_continue=None):
        if '_continue' in request.POST or '_addanother' in request.POST:
            return super().response_add(request, obj, post_url_continue)
        return self._redirigir_a_detalle(obj)

    def response_change(self, request, obj):
        if '_continue' in request.POST or '_addanother' in request.POST or '_saveasnew' in request.POST:
            return super().response_change(request, obj)
        return self._redirigir_a_detalle(obj)

    def _redirigir_a_detalle(self, obj):
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(reverse('detalle_factura', args=[obj.id]))
