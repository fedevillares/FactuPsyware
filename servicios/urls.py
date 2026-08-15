from django.urls import path
from . import views

urlpatterns = [
    path('datos/<int:servicio_id>/', views.datos_servicio, name='datos_servicio'),
]