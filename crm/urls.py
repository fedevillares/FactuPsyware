from django.urls import path
from . import views

urlpatterns = [
    path('', views.crm_dashboard, name='crm_dashboard'),
    path('pipeline/', views.kanban_leads, name='kanban_leads'),
    path('leads/nuevo/', views.nuevo_lead, name='nuevo_lead'),
    path('leads/<int:lead_id>/', views.detalle_lead, name='detalle_lead'),
    path('leads/<int:lead_id>/nota/', views.agregar_nota_lead, name='agregar_nota_lead'),
    path('leads/<int:lead_id>/actividad/', views.agregar_actividad_lead, name='agregar_actividad_lead'),
    path('actividades/<int:actividad_id>/hecha/', views.marcar_actividad_hecha, name='marcar_actividad_hecha'),
    path('leads/<int:lead_id>/estado/', views.actualizar_estado_lead, name='actualizar_estado_lead'),
    path('leads/<int:lead_id>/convertir/', views.convertir_lead, name='convertir_lead'),
    path('leads/<int:lead_id>/editar/', views.editar_lead, name='editar_lead'),
    path('clientes/<int:cliente_id>/', views.ficha_cliente, name='ficha_cliente_crm'),
]
