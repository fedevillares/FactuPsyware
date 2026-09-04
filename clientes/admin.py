from django.contrib import admin
from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo', 'tipo_doc_display', 'numero_documento', 'condicion_iva', 'telefono', 'email')
    list_display_links = ('nombre_completo',)
    list_filter = ('condicion_iva', 'tipo_documento')
    search_fields = ('nombre_completo', 'numero_documento', 'email')
    ordering = ('nombre_completo',)
    list_per_page = 50

    fieldsets = (
        ('Identificación', {
            'fields': ('nombre_completo', 'tipo_documento', 'numero_documento', 'condicion_iva'),
        }),
        ('Contacto', {
            'fields': ('telefono', 'email', 'direccion'),
        }),
        ('Soporte técnico (ticketera)', {
            'fields': ('contacto_soporte_nombre', 'contacto_soporte_email'),
            'description': 'Persona a la que se le notifican las aperturas y cierres de tickets. Distinto del email general.',
        }),
    )

    @admin.display(description='Tipo de documento', ordering='tipo_documento')
    def tipo_doc_display(self, obj):
        return obj.get_tipo_documento_display()
