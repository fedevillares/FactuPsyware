from django.contrib import admin
from .models import Cliente

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo', 'tipo_documento', 'numero_documento', 'telefono', 'condicion_iva')
    search_fields = ('nombre_completo', 'numero_documento')