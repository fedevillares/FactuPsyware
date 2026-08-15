from django.contrib import admin

from .models import Lead, NotaLead


class NotaLeadInline(admin.TabularInline):
    model = NotaLead
    extra = 0
    readonly_fields = ('fecha',)
    fields = ('texto', 'fecha')


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    inlines = [NotaLeadInline]
    list_display = ('nombre', 'estado', 'origen', 'proximo_contacto', 'cliente')
    list_display_links = ('nombre',)
    list_filter = ('estado', 'origen')
    search_fields = ('nombre', 'telefono', 'email')
    ordering = ('-actualizado',)
    autocomplete_fields = ('cliente',)
    list_select_related = ('cliente',)
