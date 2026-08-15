from django.contrib import admin

from .models import Ticket, TicketEvento


class TicketEventoInline(admin.TabularInline):
    model = TicketEvento
    extra = 0
    readonly_fields = ('fecha',)
    fields = ('tipo', 'nota', 'fecha')


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    inlines = [TicketEventoInline]
    list_display = ('numero', 'titulo', 'cliente', 'estado', 'fecha_inicio', 'fecha_fin')
    list_display_links = ('numero', 'titulo')
    list_filter = ('estado',)
    search_fields = ('titulo', 'descripcion', 'cliente__nombre_completo', 'contacto_email')
    ordering = ('-creado',)
    list_per_page = 50
    autocomplete_fields = ('cliente',)
    list_select_related = ('cliente',)

    fieldsets = (
        (None, {
            'fields': ('cliente', 'titulo', 'descripcion', 'estado'),
        }),
        ('Contacto técnico', {
            'fields': ('contacto_nombre', 'contacto_email'),
        }),
        ('Fechas', {
            'fields': ('fecha_inicio', 'fecha_fin'),
        }),
    )
    readonly_fields = ('fecha_inicio',)

    @admin.display(description='N°')
    def numero(self, obj):
        return obj.numero
