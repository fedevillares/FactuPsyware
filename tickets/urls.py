from django.urls import path
from . import views

urlpatterns = [
    path('', views.listado_tickets, name='listado_tickets'),
    path('nuevo/', views.nuevo_ticket, name='nuevo_ticket'),
    path('<int:ticket_id>/', views.detalle_ticket, name='detalle_ticket'),
    path('<int:ticket_id>/cerrar/', views.cerrar_ticket, name='cerrar_ticket'),
    path('<int:ticket_id>/reabrir/', views.reabrir_ticket, name='reabrir_ticket'),
    path('<int:ticket_id>/notificar/', views.notificar_ticket, name='notificar_ticket'),
]
