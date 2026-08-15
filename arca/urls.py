from django.urls import path
from . import views

urlpatterns = [
    path('verificacion/', views.panel_verificacion, name='panel_verificacion'),
]
