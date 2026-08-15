from django.urls import path
from . import views

urlpatterns = [
    path('', views.listado_facturas, name='listado_facturas'),
    path('<int:factura_id>/', views.detalle_factura, name='detalle_factura'),
    path('<int:factura_id>/emitir/', views.emitir, name='emitir_factura'),
    path('<int:factura_id>/comprobante/', views.comprobante, name='comprobante_factura'),
    path('<int:factura_id>/comprobante/preview/', views.comprobante_preview, name='comprobante_preview'),
    path('<int:factura_id>/nota/<str:tipo_nota>/', views.generar_nota, name='generar_nota'),
    path('<int:factura_id>/eliminar/', views.eliminar_factura, name='eliminar_factura'),
]
