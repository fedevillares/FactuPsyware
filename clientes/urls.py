from django.urls import path
from . import views

urlpatterns = [
    path('', views.listado_clientes, name='listado_clientes'),
    path('nuevo/', views.nuevo_cliente, name='nuevo_cliente'),
    path('<int:cliente_id>/editar/', views.editar_cliente, name='editar_cliente'),
    path('<int:cliente_id>/eliminar/', views.eliminar_cliente, name='eliminar_cliente'),
]
