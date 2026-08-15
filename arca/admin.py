from django.contrib import admin
from .models import EmpresaConfig


@admin.register(EmpresaConfig)
class EmpresaConfigAdmin(admin.ModelAdmin):
    list_display = ('razon_social', 'cuit')

    def has_add_permission(self, request):
        return not EmpresaConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False