"""
Tests de las barreras de seguridad e integridad del flujo de facturas.

Ninguno de estos tests llama a AFIP: cubren exclusivamente las validaciones
que cortan ANTES de contactar a ARCA (guardas de emisión, borrado, permisos
y restricciones de unicidad). El flujo real contra AFIP se prueba a mano
en homologación.
"""
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from .models import Factura, FacturaItem


def crear_cliente():
    return Cliente.objects.create(
        nombre_completo='Cliente de Prueba',
        tipo_documento='99',
        numero_documento='',
        condicion_iva='CF',
    )


def crear_factura(cliente, **kwargs):
    defaults = {'tipo_comprobante': '6', 'punto_venta': 1}
    defaults.update(kwargs)
    factura = Factura.objects.create(cliente=cliente, **defaults)
    FacturaItem.objects.create(
        factura=factura, cantidad=1, precio_unitario=100,
        alicuota_iva='5', descripcion_personalizada='Item de prueba',
    )
    return factura


class ListadoFacturasPaginacionTests(TestCase):
    """El listado de producción pagina de a 100; las métricas del encabezado
    (mes, pendientes de cobro, vencidas) se calculan sobre el filtro
    completo, no sobre la página actual."""

    def setUp(self):
        self.user = User.objects.create_user('tester_pag', password='clave-de-test')
        self.client.force_login(self.user)
        self.cliente = crear_cliente()
        self.url = reverse('listado_facturas')

    def test_pagina_1_trae_100_y_pagina_2_el_resto(self):
        for _ in range(105):
            crear_factura(self.cliente)

        respuesta = self.client.get(self.url)
        self.assertEqual(len(respuesta.context['facturas_produccion']), 100)
        self.assertContains(respuesta, 'Página 1 de 2')

        respuesta_p2 = self.client.get(self.url, {'page': 2})
        self.assertEqual(len(respuesta_p2.context['facturas_produccion']), 5)

    def test_metricas_no_cambian_entre_paginas(self):
        for _ in range(105):
            crear_factura(self.cliente)

        respuesta_p1 = self.client.get(self.url)
        respuesta_p2 = self.client.get(self.url, {'page': 2})

        self.assertEqual(respuesta_p1.context['cantidad_mes'], 105)
        self.assertEqual(respuesta_p1.context['cantidad_mes'], respuesta_p2.context['cantidad_mes'])
        self.assertEqual(respuesta_p1.context['pendientes_cobro'], respuesta_p2.context['pendientes_cobro'])

    def test_homologacion_no_se_pagina(self):
        for _ in range(3):
            crear_factura(self.cliente, entorno_emision='homologacion')

        respuesta = self.client.get(self.url)
        self.assertEqual(len(respuesta.context['facturas_homologacion']), 3)

    def test_filtro_q_se_conserva_en_el_link_de_paginacion(self):
        for _ in range(101):
            crear_factura(self.cliente)

        respuesta = self.client.get(self.url, {'q': 'Cliente de Prueba'})
        self.assertContains(respuesta, 'page=2&q=Cliente%20de%20Prueba')


class LoginRequeridoTests(TestCase):
    """Ninguna vista de facturas debe ser accesible sin iniciar sesión."""

    def test_vistas_redirigen_a_login_sin_sesion(self):
        cliente = crear_cliente()
        factura = crear_factura(cliente)
        urls = [
            reverse('listado_facturas'),
            reverse('detalle_factura', args=[factura.id]),
            reverse('comprobante_factura', args=[factura.id]),
            reverse('comprobante_preview', args=[factura.id]),
            reverse('reporte_mensual'),
        ]
        for url in urls:
            respuesta = self.client.get(url)
            self.assertEqual(respuesta.status_code, 302, url)
            self.assertIn('/accounts/login/', respuesta['Location'], url)


class EmitirGuardasTests(TestCase):
    """El POST de emisión debe validar entorno y confirmación en el servidor."""

    def setUp(self):
        self.user = User.objects.create_user('tester', password='clave-de-test')
        self.client.force_login(self.user)
        self.factura = crear_factura(crear_cliente())
        self.url = reverse('emitir_factura', args=[self.factura.id])

    def test_get_no_emite_solo_redirige(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 302)
        self.factura.refresh_from_db()
        self.assertEqual(self.factura.estado, 'BORRADOR')

    def test_entorno_faltante_rechazado(self):
        respuesta = self.client.post(self.url, {})
        self.assertContains(respuesta, 'Elegí si esta autorización')
        self.factura.refresh_from_db()
        self.assertEqual(self.factura.estado, 'BORRADOR')

    def test_entorno_invalido_rechazado(self):
        respuesta = self.client.post(self.url, {'entorno': 'otra-cosa'})
        self.assertContains(respuesta, 'Elegí si esta autorización')
        self.factura.refresh_from_db()
        self.assertEqual(self.factura.estado, 'BORRADOR')

    def test_produccion_sin_confirmacion_rechazada(self):
        respuesta = self.client.post(self.url, {'entorno': 'produccion'})
        self.assertContains(respuesta, 'tenés que escribir')
        self.factura.refresh_from_db()
        self.assertEqual(self.factura.estado, 'BORRADOR')

    def test_produccion_con_confirmacion_incorrecta_rechazada(self):
        respuesta = self.client.post(self.url, {
            'entorno': 'produccion', 'confirmacion_real': 'SI',
        })
        self.assertContains(respuesta, 'tenés que escribir')
        self.factura.refresh_from_db()
        self.assertEqual(self.factura.estado, 'BORRADOR')


class EliminarFacturaTests(TestCase):
    """Las guardas de borrado protegen los comprobantes fiscales reales."""

    def setUp(self):
        self.user = User.objects.create_user('tester', password='clave-de-test')
        self.client.force_login(self.user)
        self.cliente = crear_cliente()

    def _eliminar(self, factura):
        return self.client.post(reverse('eliminar_factura', args=[factura.id]))

    def test_borrador_se_puede_eliminar(self):
        factura = crear_factura(self.cliente)
        self._eliminar(factura)
        self.assertFalse(Factura.objects.filter(id=factura.id).exists())

    def test_autorizada_produccion_no_se_elimina(self):
        factura = crear_factura(
            self.cliente, estado='AUTORIZADA', numero=1,
            cae='12345678901234', entorno_emision='produccion',
        )
        self._eliminar(factura)
        self.assertTrue(Factura.objects.filter(id=factura.id).exists())

    def test_autorizada_homologacion_si_se_elimina(self):
        factura = crear_factura(
            self.cliente, estado='AUTORIZADA', numero=1,
            cae='12345678901234', entorno_emision='homologacion',
        )
        self._eliminar(factura)
        self.assertFalse(Factura.objects.filter(id=factura.id).exists())

    def test_emitiendo_no_se_elimina(self):
        # Una factura EMITIENDO puede tener CAE otorgado en AFIP sin guardar:
        # borrarla destruiría el único rastro local del comprobante.
        factura = crear_factura(self.cliente, estado='EMITIENDO')
        self._eliminar(factura)
        self.assertTrue(Factura.objects.filter(id=factura.id).exists())

    def test_borrado_masivo_solo_toca_homologacion(self):
        de_prueba = crear_factura(
            self.cliente, estado='AUTORIZADA', numero=1,
            cae='111', entorno_emision='homologacion',
        )
        real = crear_factura(
            self.cliente, estado='AUTORIZADA', numero=1, punto_venta=3,
            cae='222', entorno_emision='produccion',
        )
        emitiendo = crear_factura(self.cliente, estado='EMITIENDO', punto_venta=5)
        self.client.post(reverse('eliminar_facturas_homologacion'))
        self.assertFalse(Factura.objects.filter(id=de_prueba.id).exists())
        self.assertTrue(Factura.objects.filter(id=real.id).exists())
        self.assertTrue(Factura.objects.filter(id=emitiendo.id).exists())


class UnicidadNumeroTests(TestCase):
    """El número de comprobante es único por entorno + punto de venta + tipo."""

    def setUp(self):
        self.cliente = crear_cliente()

    def test_mismo_numero_en_entornos_distintos_permitido(self):
        crear_factura(
            self.cliente, numero=1, entorno_emision='homologacion',
            estado='AUTORIZADA', cae='111',
        )
        # No debe levantar IntegrityError: mismo numero/pto/tipo, otro entorno.
        crear_factura(
            self.cliente, numero=1, entorno_emision='produccion',
            estado='AUTORIZADA', cae='222',
        )
        self.assertEqual(Factura.objects.filter(numero=1).count(), 2)

    def test_mismo_numero_en_mismo_entorno_bloqueado(self):
        crear_factura(
            self.cliente, numero=1, entorno_emision='produccion',
            estado='AUTORIZADA', cae='111',
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            crear_factura(
                self.cliente, numero=1, entorno_emision='produccion',
                estado='AUTORIZADA', cae='222',
            )
