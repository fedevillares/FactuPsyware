from django.urls import path
from . import views

urlpatterns = [
    path('', views.listado_facturas, name='listado_facturas'),
    path('nueva/', views.nueva_factura, name='nueva_factura'),
    path('firma/', views.listado_facturas_firma, name='listado_facturas_firma'),
    path('<int:factura_id>/', views.detalle_factura, name='detalle_factura'),
    path('<int:factura_id>/emitir/', views.emitir, name='emitir_factura'),
    path('<int:factura_id>/cobro/', views.actualizar_cobro, name='actualizar_cobro'),
    path('<int:factura_id>/comprobante/', views.comprobante, name='comprobante_factura'),
    path('<int:factura_id>/comprobante/preview/', views.comprobante_preview, name='comprobante_preview'),
    path('<int:factura_id>/nota/editar/', views.editar_nota, name='editar_nota'),
    path('<int:factura_id>/nota/<str:tipo_nota>/', views.generar_nota, name='generar_nota'),
    path('<int:factura_id>/eliminar/', views.eliminar_factura, name='eliminar_factura'),
    path('eliminar-homologacion/', views.eliminar_facturas_homologacion, name='eliminar_facturas_homologacion'),
    path('reportes/', views.reporte_mensual, name='reporte_mensual'),
    path('enviar/preparar/', views.preparar_envio, name='preparar_envio'),
    path('enviar/', views.enviar_facturas, name='enviar_facturas'),
    path('descargar-zip/', views.descargar_zip, name='descargar_zip'),
]
