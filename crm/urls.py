from django.urls import path
from . import views

urlpatterns = [
    path('', views.kanban_leads, name='kanban_leads'),
]
