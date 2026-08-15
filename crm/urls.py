from django.urls import path
from . import views

urlpatterns = [
    path('', views.kanban_leads, name='kanban_leads'),
    path('leads/nuevo/', views.nuevo_lead, name='nuevo_lead'),
    path('leads/<int:lead_id>/', views.detalle_lead, name='detalle_lead'),
    path('leads/<int:lead_id>/nota/', views.agregar_nota_lead, name='agregar_nota_lead'),
]
