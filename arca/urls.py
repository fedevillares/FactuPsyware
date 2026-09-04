from django.urls import path
from . import views

urlpatterns = [
    path('verificacion/', views.panel_verificacion, name='panel_verificacion'),
    path('verificacion/probar-email/', views.probar_email, name='probar_email'),
    path('backup/', views.panel_backup, name='panel_backup'),
    path('backup/exportar/', views.exportar_db, name='exportar_db'),
    path('backup/guardar/', views.guardar_backup_local, name='guardar_backup_local'),
    path('backup/importar/', views.importar_db, name='importar_db'),
    path('backup/eliminar/', views.eliminar_backup, name='eliminar_backup'),
    path('backup/descargar/', views.descargar_backup_local, name='descargar_backup_local'),
]
