from django.urls import path
from . import views

urlpatterns = [
    path('', views.listado_servicios, name='listado_servicios'),
    path('nuevo/', views.nuevo_servicio, name='nuevo_servicio'),
    path('<int:servicio_id>/editar/', views.editar_servicio, name='editar_servicio'),
    path('<int:servicio_id>/eliminar/', views.eliminar_servicio, name='eliminar_servicio'),
    path('<int:servicio_id>/alternar-activo/', views.alternar_activo, name='alternar_activo_servicio'),
    path('aumento/', views.aplicar_aumento, name='aplicar_aumento_servicios'),
    path('datos/<int:servicio_id>/', views.datos_servicio, name='datos_servicio'),
]
