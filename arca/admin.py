from django import forms
from django.contrib import admin
from django.utils.html import format_html
from .models import EmpresaConfig


class EmpresaConfigForm(forms.ModelForm):
    email_password = forms.CharField(
        required=False, widget=forms.PasswordInput(render_value=False),
        label='Contraseña / clave de aplicación',
        help_text="Para Gmail, usar una 'contraseña de aplicación'. Dejar en blanco para no cambiarla — nunca se muestra la guardada.",
    )

    class Meta:
        model = EmpresaConfig
        fields = '__all__'

    def clean_email_password(self):
        from .crypto import cifrar
        nuevo = self.cleaned_data.get('email_password', '').strip()
        if not nuevo:
            # Sin cambios: conservar el valor cifrado ya guardado.
            return self.instance.email_password
        return cifrar(nuevo)


@admin.register(EmpresaConfig)
class EmpresaConfigAdmin(admin.ModelAdmin):
    form = EmpresaConfigForm
    list_display = ('razon_social', 'cuit', 'condicion_iva')
    readonly_fields = ('logo_preview',)

    fieldsets = (
        ('Datos fiscales', {
            'fields': ('logo', 'logo_preview', 'nombre_fantasia', 'razon_social', 'cuit', 'condicion_iva', 'ingresos_brutos', 'inicio_actividades'),
        }),
        ('Domicilio y contacto', {
            'fields': ('domicilio', 'localidad', 'telefono'),
        }),
        ('Facturación', {
            'fields': ('punto_venta_defecto', 'otros_impuestos_pct', 'leyenda'),
        }),
        ('Envío de facturas por email', {
            'fields': ('email_nombre_remitente', 'email_remitente', 'email_password', 'email_host', 'email_port', 'email_use_tls'),
            'description': 'Datos de la cuenta de correo desde la que se envían las facturas a los clientes. Para Gmail, generar una "contraseña de aplicación" en la configuración de seguridad de la cuenta de Google.',
        }),
    )

    def has_add_permission(self, request):
        return not EmpresaConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Vista previa del logo')
    def logo_preview(self, obj):
        if not obj.logo:
            return "Todavía no subiste ningún logo."
        return format_html(
            '<img src="{}" style="max-width:400px; max-height:160px; object-fit:contain; background:#fff; border:1px solid var(--border, #ccc); padding:8px; border-radius:6px;">',
            obj.logo.url,
        )