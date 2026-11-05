from django.core.management.base import BaseCommand

from tickets.correo_entrante import revisar_bandeja


class Command(BaseCommand):
    help = ('Revisa una vez la bandeja de la cuenta de soporte y abre tickets por los '
            'correos con asunto "TICKET DE SOPORTE" (sin importar si la recepción '
            'automática está activada).')

    def handle(self, *args, **options):
        resultado = revisar_bandeja()
        estilo = self.style.ERROR if resultado.error else self.style.SUCCESS
        self.stdout.write(estilo(resultado.resumen()))
        for ticket in resultado.creados:
            self.stdout.write(f"  {ticket.numero} — {ticket.cliente.nombre_completo} — {ticket.contacto_email}")
