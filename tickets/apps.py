from django.apps import AppConfig


class TicketsConfig(AppConfig):
    name = 'tickets'
    verbose_name = 'Soporte técnico'

    def ready(self):
        # Revisión periódica de la bandeja de soporte (abre tickets desde los
        # correos con asunto "TICKET DE SOPORTE"). Solo corre dentro del
        # servidor; cada ciclo verifica si la recepción está activada.
        from .correo_entrante import debe_iniciar_hilo, iniciar_revision_periodica
        if debe_iniciar_hilo():
            iniciar_revision_periodica()
