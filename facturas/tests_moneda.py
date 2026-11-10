"""
Tests de la facturación en dólares (moneda + cotización).

Ninguno llama a ARCA ni a las APIs de cotización: todo lo externo está
mockeado (requests.get, el cliente SOAP de WSFE y la generación de la imagen
del QR).
"""
import base64
import datetime
import json
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import mock, skipUnless

import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from arca.models import EmpresaConfig
from clientes.models import Cliente
from . import cotizaciones
from .models import Factura, FacturaItem
from .moneda import calcular_totales, formato_ar, formato_cotizacion, redondear

FECHA_API = datetime.datetime(2026, 11, 5, 18, 55, tzinfo=datetime.timezone.utc)


def crear_cliente(**kwargs):
    datos = {
        'nombre_completo': 'Cliente de Prueba', 'tipo_documento': '80',
        'numero_documento': '20111111112', 'condicion_iva': 'RI',
    }
    datos.update(kwargs)
    return Cliente.objects.create(**datos)


def crear_factura(cliente, items, **kwargs):
    """items: lista de (cantidad, precio, alícuota)."""
    datos = {'tipo_comprobante': '1', 'punto_venta': 1}
    datos.update(kwargs)
    factura = Factura.objects.create(cliente=cliente, **datos)
    for cantidad, precio, alicuota in items:
        FacturaItem.objects.create(
            factura=factura, cantidad=Decimal(cantidad), precio_unitario=Decimal(precio),
            alicuota_iva=alicuota, descripcion_personalizada='Item de prueba',
        )
    return factura


def crear_factura_usd(cliente, items=None, **kwargs):
    datos = {
        'moneda': 'USD', 'cotizacion': Decimal('1435.50'),
        'cotizacion_fuente': 'api:dolarapi', 'cotizacion_fecha': FECHA_API,
    }
    datos.update(kwargs)
    return crear_factura(cliente, items or [('1', '100.00', '5')], **datos)


def cotizacion_falsa(valor='1570', fuente='api:dolarapi', desactualizada=False):
    return {
        'valor': Decimal(valor), 'fuente': fuente, 'fecha': FECHA_API,
        'tipo': 'oficial', 'campo': 'venta', 'desactualizada': desactualizada,
    }


def item(cantidad, precio, alicuota):
    return SimpleNamespace(
        cantidad=Decimal(cantidad), precio_unitario=Decimal(precio), alicuota_iva=alicuota,
    )


# ── Cálculo ─────────────────────────────────────────────────────────────────

class CalculoTotalesTests(SimpleTestCase):
    def test_iva_por_alicuota_en_dolares(self):
        totales = calcular_totales(
            [item('2', '150.00', '5'), item('1', '80.00', '4'), item('3', '10.00', '3')],
            Decimal('1435.50'),
        )
        self.assertEqual(totales['neto'], Decimal('410.00'))
        iva = {a['codigo']: a['iva'] for a in totales['alicuotas']}
        self.assertEqual(iva['5'], Decimal('63.00'))     # 21% de 300
        self.assertEqual(iva['4'], Decimal('8.40'))      # 10,5% de 80
        self.assertEqual(iva['3'], Decimal('0.00'))
        self.assertEqual(totales['iva'], Decimal('71.40'))
        self.assertEqual(totales['total'], Decimal('481.40'))

    def test_siempre_devuelve_las_seis_alicuotas_de_mayor_a_menor(self):
        totales = calcular_totales([item('1', '100', '5')])
        self.assertEqual(
            [a['porcentaje'] for a in totales['alicuotas']],
            [Decimal('27'), Decimal('21'), Decimal('10.5'), Decimal('5'), Decimal('2.5'), Decimal('0')],
        )

    def test_redondeo_half_up(self):
        # 0,125 -> 0,13 (round() de Python / half-even daría 0,12)
        self.assertEqual(redondear(Decimal('0.125')), Decimal('0.13'))
        self.assertEqual(redondear(Decimal('0.135')), Decimal('0.14'))
        self.assertEqual(redondear(Decimal('2.675')), Decimal('2.68'))
        # 1 × 0,50 al 2,5% = 0,0125 -> 0,01 ; 1 × 1,00 al 2,5% = 0,025 -> 0,03
        self.assertEqual(calcular_totales([item('1', '0.50', '9')])['iva'], Decimal('0.01'))
        self.assertEqual(calcular_totales([item('1', '1.00', '9')])['iva'], Decimal('0.03'))
        # cantidad × precio con medio centavo: 0,5 × 0,25 = 0,125 -> 0,13
        self.assertEqual(calcular_totales([item('0.5', '0.25', '3')])['neto'], Decimal('0.13'))

    def test_todo_es_decimal_nunca_float(self):
        totales = calcular_totales([item('1.5', '33.33', '5')], Decimal('1234.567891'))
        for clave in ('neto', 'iva', 'total', 'neto_ars', 'iva_ars', 'total_ars'):
            self.assertIsInstance(totales[clave], Decimal, clave)
            self.assertEqual(totales[clave], totales[clave].quantize(Decimal('0.01')), clave)

    def test_conversion_a_pesos(self):
        totales = calcular_totales([item('1', '100.00', '5')], Decimal('1435.50'))
        self.assertEqual(totales['total'], Decimal('121.00'))
        self.assertEqual(totales['total_ars'], Decimal('173695.50'))   # 121 × 1435,50
        self.assertEqual(totales['iva_ars'], Decimal('30145.50'))      # 21 × 1435,50
        self.assertEqual(totales['neto_ars'], Decimal('143550.00'))

    def test_conversion_a_pesos_siempre_cuadra(self):
        """neto + IVA == total también en pesos, aunque convertir cada parte
        por separado descuadre un centavo."""
        totales = calcular_totales(
            [item('1', '33.33', '5'), item('1', '33.33', '4'), item('1', '33.33', '6')],
            Decimal('1234.567891'),
        )
        self.assertEqual(totales['neto_ars'] + totales['iva_ars'], totales['total_ars'])
        self.assertEqual(totales['total_ars'], redondear(totales['total'] * Decimal('1234.567891')))
        self.assertEqual(totales['iva_ars'], sum(a['iva_ars'] for a in totales['alicuotas']))

    def test_cotizacion_1_equivale_a_pesos(self):
        totales = calcular_totales([item('3', '1234.56', '5')])
        self.assertEqual(totales['total_ars'], totales['total'])
        self.assertEqual(totales['neto_ars'], totales['neto'])

    def test_formato_argentino(self):
        self.assertEqual(formato_ar(Decimal('1234567.891')), '1.234.567,89')
        self.assertEqual(formato_ar(Decimal('-1234.5')), '-1.234,50')
        self.assertEqual(formato_ar(Decimal('0')), '0,00')
        self.assertEqual(formato_ar(Decimal('1435.5'), 6), '1.435,500000')
        self.assertEqual(formato_cotizacion(Decimal('1570')), '1.570,00')
        self.assertEqual(formato_cotizacion(Decimal('1435.125000')), '1.435,125')
        self.assertEqual(formato_cotizacion(Decimal('0.000001')), '0,000001')


@skipUnless(shutil.which('node'), 'node no está instalado')
class TotalesEnVivoCoincidenConBackendTests(SimpleTestCase):
    """El cálculo en vivo del formulario (JS) tiene que dar exactamente lo
    mismo que el backend."""

    def test_js_igual_a_python(self):
        casos = [
            ([('1', '100.00', '5')], '1435.50'),
            ([('0.5', '0.25', '3'), ('1', '0.50', '9'), ('1', '1.00', '9')], '1'),
            ([('1', '33.33', '5'), ('1', '33.33', '4'), ('1', '33.33', '6')], '1234.567891'),
            ([('2.75', '1999.99', '5'), ('13', '0.07', '8'), ('1.01', '45678.90', '4')], '1570'),
            ([('3', '0.01', '6'), ('7.77', '7.77', '9')], '0.000001'),
            ([('1000000', '99999.99', '5')], '9999.999999'),
        ]
        entrada = [
            {'items': [{'cantidad': c, 'precio_unitario': p, 'alicuota_iva': a} for c, p, a in items],
             'cotizacion': cotizacion}
            for items, cotizacion in casos
        ]
        script = Path(settings.BASE_DIR) / 'static' / 'js' / 'factura_totales.js'
        programa = (
            "const {calcularTotalesFactura} = require(process.argv[1]);"
            "const casos = JSON.parse(process.argv[2]);"
            "console.log(JSON.stringify(casos.map(c => calcularTotalesFactura(c.items, c.cotizacion))));"
        )
        salida = subprocess.run(
            ['node', '-e', programa, str(script), json.dumps(entrada)],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout
        resultados_js = json.loads(salida)

        for (items, cotizacion), js in zip(casos, resultados_js):
            py = calcular_totales([item(*i) for i in items], Decimal(cotizacion))
            for clave in ('neto', 'iva', 'total', 'neto_ars', 'iva_ars', 'total_ars'):
                self.assertEqual(Decimal(js[clave]), py[clave], f"{clave} en {items} @ {cotizacion}")
            for a_js, a_py in zip(js['alicuotas'], py['alicuotas']):
                self.assertEqual(a_js['codigo'], a_py['codigo'])
                self.assertEqual(Decimal(a_js['iva']), a_py['iva'])
                self.assertEqual(Decimal(a_js['iva_ars']), a_py['iva_ars'])


# ── Servicio de cotización ──────────────────────────────────────────────────

def respuesta_http(datos):
    respuesta = mock.Mock()
    respuesta.json.return_value = datos
    respuesta.raise_for_status.return_value = None
    return respuesta


DOLARAPI_OK = {
    'moneda': 'USD', 'casa': 'oficial', 'nombre': 'Oficial',
    'compra': 1520, 'venta': 1570, 'fechaActualizacion': '2026-11-05T18:55:00.000Z',
}
BLUELYTICS_OK = {
    'oficial': {'value_avg': 1545.00, 'value_sell': 1572.00, 'value_buy': 1518.00},
    'blue': {'value_avg': 1538.50, 'value_sell': 1555.00, 'value_buy': 1522.00},
    'last_update': '2026-11-10T17:15:52.478699-03:00',
}


class ServicioCotizacionTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    @mock.patch('facturas.cotizaciones.requests.get')
    def test_proveedor_principal(self, get):
        get.return_value = respuesta_http(DOLARAPI_OK)
        cotizacion = cotizaciones.get_rate()
        self.assertEqual(cotizacion['valor'], Decimal('1570'))
        self.assertIsInstance(cotizacion['valor'], Decimal)
        self.assertEqual(cotizacion['fuente'], 'api:dolarapi')
        self.assertEqual(cotizacion['fecha'], FECHA_API)
        self.assertFalse(cotizacion['desactualizada'])
        url = get.call_args.args[0]
        self.assertEqual(url, 'https://dolarapi.com/v1/dolares/oficial')
        self.assertEqual(get.call_args.kwargs['timeout'], settings.COTIZACION_TIMEOUT_SEGUNDOS)

    @mock.patch('facturas.cotizaciones.requests.get')
    def test_fallback_a_bluelytics_si_falla_dolarapi(self, get):
        get.side_effect = [requests.Timeout('timeout'), respuesta_http(BLUELYTICS_OK)]
        cotizacion = cotizaciones.get_rate()
        self.assertEqual(cotizacion['valor'], Decimal('1572'))
        self.assertEqual(cotizacion['fuente'], 'api:bluelytics')
        self.assertEqual(get.call_count, 2)

    @mock.patch('facturas.cotizaciones.requests.get')
    def test_fallback_si_dolarapi_devuelve_basura(self, get):
        get.side_effect = [respuesta_http({'venta': 0}), respuesta_http(BLUELYTICS_OK)]
        self.assertEqual(cotizaciones.get_rate()['fuente'], 'api:bluelytics')

    @mock.patch('facturas.cotizaciones.requests.get')
    def test_sin_proveedores_y_sin_cache_lanza_error(self, get):
        get.side_effect = requests.ConnectionError('sin red')
        with self.assertRaises(cotizaciones.CotizacionNoDisponible):
            cotizaciones.get_rate()

    @mock.patch('facturas.cotizaciones.requests.get')
    def test_cache_evita_segunda_llamada(self, get):
        get.return_value = respuesta_http(DOLARAPI_OK)
        cotizaciones.get_rate()
        cotizaciones.get_rate()
        self.assertEqual(get.call_count, 1)

    @mock.patch('facturas.cotizaciones.requests.get')
    def test_forzar_saltea_el_cache(self, get):
        get.return_value = respuesta_http(DOLARAPI_OK)
        cotizaciones.get_rate()
        cotizaciones.get_rate(forzar=True)
        self.assertEqual(get.call_count, 2)

    @mock.patch('facturas.cotizaciones.requests.get')
    def test_si_todo_falla_usa_la_ultima_obtenida(self, get):
        get.return_value = respuesta_http(DOLARAPI_OK)
        cotizaciones.get_rate()
        get.side_effect = requests.ConnectionError('sin red')
        cotizacion = cotizaciones.get_rate(forzar=True)
        self.assertEqual(cotizacion['valor'], Decimal('1570'))
        self.assertTrue(cotizacion['desactualizada'])

    @mock.patch('facturas.cotizaciones.requests.get')
    def test_tipo_y_campo_configurables(self, get):
        get.return_value = respuesta_http(DOLARAPI_OK)
        with self.settings(COTIZACION_DOLAR_TIPO='mayorista', COTIZACION_DOLAR_CAMPO='compra'):
            cotizacion = cotizaciones.get_rate()
        self.assertEqual(get.call_args.args[0], 'https://dolarapi.com/v1/dolares/mayorista')
        self.assertEqual(cotizacion['valor'], Decimal('1520'))

    def test_desvio_porcentual(self):
        self.assertEqual(cotizaciones.desvio_porcentual(Decimal('1727'), Decimal('1570')), Decimal('10'))
        self.assertEqual(cotizaciones.desvio_porcentual(Decimal('1413'), Decimal('1570')), Decimal('10'))


# ── Vistas ──────────────────────────────────────────────────────────────────

class VistasBase(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user('tester_usd', password='clave-de-test')
        self.client.force_login(self.user)
        self.cliente = crear_cliente()

    def datos_form(self, **extra):
        datos = {
            'cliente': self.cliente.id, 'tipo_comprobante': '1', 'punto_venta': '1',
            'condicion_venta': 'TRANSFERENCIA',
            'nuevo_servicio[]': [''], 'nueva_descripcion[]': ['Consultoría'],
            'nueva_cantidad[]': ['2'], 'nuevo_precio[]': ['150.00'], 'nueva_alicuota[]': ['5'],
        }
        datos.update(extra)
        return datos


class EndpointCotizacionTests(VistasBase):
    def test_requiere_login(self):
        self.client.logout()
        respuesta = self.client.get(reverse('cotizacion_dolar'))
        self.assertEqual(respuesta.status_code, 302)

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_devuelve_la_cotizacion(self, get_rate):
        get_rate.return_value = cotizacion_falsa('1570.5')
        datos = self.client.get(reverse('cotizacion_dolar')).json()
        self.assertTrue(datos['ok'])
        self.assertEqual(datos['valor'], '1570.5')
        self.assertEqual(datos['fuente'], 'api:dolarapi')
        self.assertEqual(datos['fecha_texto'], '05/11/2026 15:55')     # hora de Buenos Aires
        get_rate.assert_called_once_with(forzar=False)

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_boton_actualizar_fuerza_la_consulta(self, get_rate):
        get_rate.return_value = cotizacion_falsa()
        self.client.get(reverse('cotizacion_dolar'), {'forzar': '1'})
        get_rate.assert_called_once_with(forzar=True)

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_si_falla_no_rompe(self, get_rate):
        get_rate.side_effect = cotizaciones.CotizacionNoDisponible('sin cotización')
        respuesta = self.client.get(reverse('cotizacion_dolar'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {'ok': False, 'error': 'sin cotización'})


class NuevaFacturaMonedaTests(VistasBase):
    url = property(lambda self: reverse('nueva_factura'))

    def test_formulario_muestra_selector_de_moneda(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'name="moneda"')
        self.assertContains(respuesta, 'id="bloque-cotizacion"')
        self.assertContains(respuesta, 'js/factura_totales.js')

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_regresion_factura_en_pesos(self, get_rate):
        """Sin tocar nada de moneda, la factura queda en pesos con cotización 1
        y no se consulta ninguna API."""
        respuesta = self.client.post(self.url, self.datos_form())
        factura = Factura.objects.get()
        self.assertRedirects(respuesta, reverse('detalle_factura', args=[factura.id]))
        self.assertEqual(factura.moneda, 'ARS')
        self.assertEqual(factura.cotizacion, Decimal('1'))
        self.assertEqual(factura.cotizacion_fuente, '')
        self.assertIsNone(factura.cotizacion_fecha)
        self.assertFalse(factura.cancela_misma_moneda)
        get_rate.assert_not_called()

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_pesos_ignora_una_cotizacion_enviada(self, get_rate):
        self.client.post(self.url, self.datos_form(
            moneda='ARS', cotizacion_modo='manual', cotizacion='1500', cancela_misma_moneda='1'))
        factura = Factura.objects.get()
        self.assertEqual(factura.cotizacion, Decimal('1'))
        self.assertFalse(factura.cancela_misma_moneda)

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_dolares_automatico_guarda_la_cotizacion_de_la_api(self, get_rate):
        get_rate.return_value = cotizacion_falsa('1570')
        # El valor que manda el navegador se ignora: manda el servidor.
        self.client.post(self.url, self.datos_form(moneda='USD', cotizacion_modo='auto', cotizacion='1'))
        factura = Factura.objects.get()
        self.assertEqual(factura.moneda, 'USD')
        self.assertEqual(factura.cotizacion, Decimal('1570'))
        self.assertEqual(factura.cotizacion_fuente, 'api:dolarapi')
        self.assertEqual(factura.cotizacion_fecha, FECHA_API)
        totales = factura.totales
        self.assertEqual(totales['total'], Decimal('363.00'))
        self.assertEqual(totales['total_ars'], Decimal('569910.00'))

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_dolares_manual_es_override(self, get_rate):
        get_rate.return_value = cotizacion_falsa('1570')
        antes = timezone.now()
        self.client.post(self.url, self.datos_form(
            moneda='USD', cotizacion_modo='manual', cotizacion='1600,25', cancela_misma_moneda='1'))
        factura = Factura.objects.get()
        self.assertEqual(factura.cotizacion, Decimal('1600.25'))
        self.assertEqual(factura.cotizacion_fuente, 'manual')
        self.assertGreaterEqual(factura.cotizacion_fecha, antes)
        self.assertTrue(factura.cancela_misma_moneda)

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_dolares_sin_cotizacion_no_se_permite(self, get_rate):
        get_rate.return_value = cotizacion_falsa('1570')
        respuesta = self.client.post(self.url, self.datos_form(
            moneda='USD', cotizacion_modo='manual', cotizacion=''))
        self.assertEqual(Factura.objects.count(), 0)
        self.assertContains(respuesta, 'ingresá la cotización')

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_cotizacion_cero_o_negativa_rechazada(self, get_rate):
        get_rate.return_value = cotizacion_falsa('1570')
        for valor in ('0', '-5', 'abc'):
            respuesta = self.client.post(self.url, self.datos_form(
                moneda='USD', cotizacion_modo='manual', cotizacion=valor))
            self.assertEqual(respuesta.status_code, 200, valor)
            self.assertEqual(Factura.objects.count(), 0, valor)

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_manual_con_desvio_mayor_al_10_pide_confirmacion(self, get_rate):
        get_rate.return_value = cotizacion_falsa('1570')
        datos = self.datos_form(moneda='USD', cotizacion_modo='manual', cotizacion='1800')
        respuesta = self.client.post(self.url, datos)
        self.assertEqual(Factura.objects.count(), 0)
        self.assertContains(respuesta, 'se desvía un 14.6%')
        self.assertTrue(respuesta.context['pedir_confirmacion_desvio'])
        # Se conserva lo que escribió el usuario.
        self.assertContains(respuesta, 'value="1800"')

        self.client.post(self.url, {**datos, 'confirmar_desvio': '1'})
        self.assertEqual(Factura.objects.get().cotizacion, Decimal('1800'))

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_manual_dentro_del_10_no_pide_confirmacion(self, get_rate):
        get_rate.return_value = cotizacion_falsa('1570')
        self.client.post(self.url, self.datos_form(moneda='USD', cotizacion_modo='manual', cotizacion='1700'))
        self.assertEqual(Factura.objects.get().cotizacion, Decimal('1700'))

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_api_caida_automatico_pide_carga_manual(self, get_rate):
        get_rate.side_effect = cotizaciones.CotizacionNoDisponible('x')
        respuesta = self.client.post(self.url, self.datos_form(moneda='USD', cotizacion_modo='auto'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Factura.objects.count(), 0)
        self.assertContains(respuesta, 'Elegí el modo Manual')

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_api_caida_manual_funciona_igual(self, get_rate):
        get_rate.side_effect = cotizaciones.CotizacionNoDisponible('x')
        self.client.post(self.url, self.datos_form(moneda='USD', cotizacion_modo='manual', cotizacion='1580'))
        factura = Factura.objects.get()
        self.assertEqual(factura.cotizacion, Decimal('1580'))
        self.assertEqual(factura.cotizacion_fuente, 'manual')

    def test_moneda_invalida_rechazada(self):
        self.client.post(self.url, self.datos_form(moneda='EUR'))
        self.assertEqual(Factura.objects.count(), 0)


class DetalleYCotizacionDelBorradorTests(VistasBase):
    def test_detalle_en_dolares_muestra_cotizacion_y_equivalente(self):
        factura = crear_factura_usd(self.cliente)
        respuesta = self.client.get(reverse('detalle_factura', args=[factura.id]))
        self.assertContains(respuesta, 'US$ 121,00')
        self.assertContains(respuesta, 'Dólar Estadounidense (DOL)')
        self.assertContains(respuesta, '$ 1.435,50')
        self.assertContains(respuesta, '173.695,50')      # total en pesos
        self.assertContains(respuesta, '30.145,50')       # IVA 21% en pesos
        self.assertContains(respuesta, 'Automática (dolarapi)')
        self.assertContains(respuesta, 'Guardar cotización')

    def test_detalle_en_pesos_no_muestra_bloque_de_moneda(self):
        factura = crear_factura(self.cliente, [('1', '100.00', '5')])
        respuesta = self.client.get(reverse('detalle_factura', args=[factura.id]))
        self.assertContains(respuesta, '$ 121,00')
        self.assertNotContains(respuesta, 'US$')
        self.assertNotContains(respuesta, 'moneda-extranjera')

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_borrador_permite_cambiar_la_cotizacion(self, get_rate):
        get_rate.return_value = cotizacion_falsa('1570')
        factura = crear_factura_usd(self.cliente)
        self.client.post(reverse('actualizar_cotizacion', args=[factura.id]),
                         {'cotizacion_modo': 'manual', 'cotizacion': '1500'})
        factura.refresh_from_db()
        self.assertEqual(factura.cotizacion, Decimal('1500'))
        self.assertEqual(factura.cotizacion_fuente, 'manual')

        self.client.post(reverse('actualizar_cotizacion', args=[factura.id]), {'cotizacion_modo': 'auto'})
        factura.refresh_from_db()
        self.assertEqual(factura.cotizacion, Decimal('1570'))
        self.assertEqual(factura.cotizacion_fuente, 'api:dolarapi')

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_autorizada_es_inmutable(self, get_rate):
        get_rate.return_value = cotizacion_falsa('1570')
        factura = crear_factura_usd(
            self.cliente, estado='AUTORIZADA', numero=1, cae='12345678901234',
            cae_vencimiento=datetime.date(2026, 11, 20), entorno_emision='produccion',
        )
        self.client.post(reverse('actualizar_cotizacion', args=[factura.id]),
                         {'cotizacion_modo': 'manual', 'cotizacion': '1500'})
        factura.refresh_from_db()
        self.assertEqual(factura.cotizacion, Decimal('1435.50'))
        self.assertEqual(factura.cotizacion_fuente, 'api:dolarapi')
        respuesta = self.client.get(reverse('detalle_factura', args=[factura.id]))
        self.assertNotContains(respuesta, 'Guardar cotización')
        self.assertContains(respuesta, 'La cotización quedó fija')

    def test_factura_en_pesos_no_admite_cambio_de_cotizacion(self):
        factura = crear_factura(self.cliente, [('1', '100.00', '5')])
        self.client.post(reverse('actualizar_cotizacion', args=[factura.id]),
                         {'cotizacion_modo': 'manual', 'cotizacion': '1500'})
        factura.refresh_from_db()
        self.assertEqual(factura.cotizacion, Decimal('1'))

    def test_nota_de_credito_hereda_moneda_y_cotizacion(self):
        factura = crear_factura_usd(
            self.cliente, estado='AUTORIZADA', numero=1, cae='12345678901234',
            cae_vencimiento=datetime.date(2026, 11, 20), entorno_emision='homologacion',
            cancela_misma_moneda=True,
        )
        self.client.post(reverse('generar_nota', args=[factura.id, 'credito']))
        nota = Factura.objects.get(factura_asociada=factura)
        self.assertEqual(nota.moneda, 'USD')
        self.assertEqual(nota.cotizacion, Decimal('1435.50'))
        self.assertEqual(nota.cotizacion_fuente, 'api:dolarapi')
        self.assertTrue(nota.cancela_misma_moneda)


class ReporteMensualPorMonedaTests(VistasBase):
    def autorizada(self, numero, **kwargs):
        datos = {
            'estado': 'AUTORIZADA', 'numero': numero, 'cae': '12345678901234',
            'cae_vencimiento': datetime.date(2026, 11, 20), 'entorno_emision': 'produccion',
        }
        datos.update(kwargs)
        return datos

    def test_metricas_separadas_por_moneda(self):
        crear_factura(self.cliente, [('1', '1000.00', '5')],
                      **self.autorizada(1, pagada=True, retencion_iva=Decimal('50')))
        crear_factura(self.cliente, [('1', '500.00', '5')], **self.autorizada(2))
        crear_factura_usd(self.cliente, [('1', '100.00', '5')],
                          **self.autorizada(3, cotizacion=Decimal('1500'), pagada=True))
        crear_factura_usd(self.cliente, [('1', '200.00', '4')],
                          **self.autorizada(4, cotizacion=Decimal('1600'),
                                            retencion_ganancias=Decimal('1000')))
        # Nota de crédito en dólares por 50 + IVA
        crear_factura_usd(self.cliente, [('1', '50.00', '5')],
                          **self.autorizada(1, tipo_comprobante='3', cotizacion=Decimal('1500')))

        respuesta = self.client.get(reverse('reporte_mensual'))
        ars, usd = respuesta.context['metricas_por_moneda']

        self.assertEqual(ars['moneda'], 'ARS')
        self.assertEqual(ars['neto_facturado'], Decimal('1500.00'))
        self.assertEqual(ars['iva'], Decimal('315.00'))
        self.assertEqual(ars['total_general'], Decimal('1815.00'))
        self.assertEqual(ars['neto_cobrado'], Decimal('1000.00'))
        self.assertEqual(ars['pendiente_cobro'], Decimal('605.00'))
        self.assertEqual(ars['retenciones'], Decimal('50.00'))

        self.assertEqual(usd['moneda'], 'USD')
        self.assertEqual(usd['simbolo'], 'US$')
        self.assertEqual(usd['neto_facturado'], Decimal('250.00'))        # 100 + 200 − 50
        self.assertEqual(usd['iva'], Decimal('31.50'))                    # 21 + 21 − 10,50
        self.assertEqual(usd['devuelto'], Decimal('60.50'))
        self.assertEqual(usd['neto_cobrado'], Decimal('100.00'))
        self.assertEqual(usd['pendiente_cobro'], Decimal('221.00'))
        self.assertEqual(usd['retenciones'], Decimal('1000.00'))
        # Cada comprobante con SU cotización: 121×1500 + 221×1600 − 60,50×1500
        self.assertEqual(usd['total_ars'], Decimal('444350.00'))

        self.assertEqual(respuesta.context['total_convertido_ars'], Decimal('446165.00'))
        self.assertTrue(respuesta.context['hay_moneda_extranjera'])
        self.assertContains(respuesta, 'US$ 250,00')
        self.assertContains(respuesta, 'Total convertido a pesos')

    def test_regresion_solo_pesos(self):
        crear_factura(self.cliente, [('1', '1000.00', '5')], **self.autorizada(1))
        respuesta = self.client.get(reverse('reporte_mensual'))
        self.assertEqual(len(respuesta.context['metricas_por_moneda']), 1)
        self.assertFalse(respuesta.context['hay_moneda_extranjera'])
        self.assertContains(respuesta, '$ 1.210,00')
        self.assertNotContains(respuesta, 'US$')
        self.assertNotContains(respuesta, 'Total convertido a pesos')

    def test_listado_muestra_simbolo_de_cada_moneda(self):
        crear_factura(self.cliente, [('1', '1000.00', '5')])
        crear_factura_usd(self.cliente)
        respuesta = self.client.get(reverse('listado_facturas'))
        self.assertContains(respuesta, '$ 1.210,00')
        self.assertContains(respuesta, 'US$ 121,00')


# ── ARCA: WSFE y QR (todo mockeado) ─────────────────────────────────────────

DATOS_ENTORNO = {'entorno': 'homologacion', 'wsfe_url': 'https://wsfe.invalid/?WSDL'}


def cliente_soap_falso():
    cliente = mock.Mock()
    cliente.service.FECompUltimoAutorizado.return_value = SimpleNamespace(CbteNro=41)
    cliente.service.FECAESolicitar.return_value = SimpleNamespace(
        Errors=None,
        FeDetResp=SimpleNamespace(FECAEDetResponse=[SimpleNamespace(
            Resultado='A', CAE='76123456789012', CAEFchVto='20261120', Observaciones=None,
        )]),
    )
    return cliente


@mock.patch('arca.wsfe.config.CUIT', '20000000001')
class WsfeMonedaTests(TestCase):
    def setUp(self):
        self.cliente = crear_cliente()

    def solicitar(self, factura):
        from arca import wsfe
        soap = cliente_soap_falso()
        with mock.patch('arca.wsfe.get_client', return_value=soap):
            resultado = wsfe.solicitar_cae('token', 'sign', factura, DATOS_ENTORNO)
        if not soap.service.FECAESolicitar.called:
            return resultado, None
        pedido = soap.service.FECAESolicitar.call_args.kwargs['FeCAEReq']
        return resultado, pedido['FeDetReq']['FECAEDetRequest'][0]

    def test_dolares_envia_dol_cotizacion_e_importes_en_dolares(self):
        factura = crear_factura_usd(
            self.cliente, [('2', '150.00', '5'), ('1', '80.00', '4')], cotizacion=Decimal('1435.50'))
        resultado, detalle = self.solicitar(factura)
        self.assertTrue(resultado['ok'])
        self.assertEqual(resultado['numero'], 42)
        self.assertEqual(detalle['MonId'], 'DOL')
        self.assertEqual(detalle['MonCotiz'], 1435.5)
        self.assertEqual(detalle['CanMisMonExt'], 'N')
        # Importes en la moneda del comprobante (dólares), no convertidos.
        self.assertEqual(detalle['ImpNeto'], 380.0)
        self.assertEqual(detalle['ImpIVA'], 71.4)
        self.assertEqual(detalle['ImpTotal'], 451.4)
        alicuotas = {a['Id']: a for a in detalle['Iva']['AlicIva']}
        self.assertEqual(set(alicuotas), {4, 5})
        self.assertEqual(alicuotas[5], {'Id': 5, 'BaseImp': 300.0, 'Importe': 63.0})
        self.assertEqual(alicuotas[4], {'Id': 4, 'BaseImp': 80.0, 'Importe': 8.4})
        # Consistencia que valida ARCA
        self.assertEqual(round(detalle['ImpNeto'] + detalle['ImpIVA'], 2), detalle['ImpTotal'])

    def test_cancela_en_misma_moneda_informa_s(self):
        factura = crear_factura_usd(self.cliente, cancela_misma_moneda=True)
        _, detalle = self.solicitar(factura)
        self.assertEqual(detalle['CanMisMonExt'], 'S')

    def test_cotizacion_con_seis_decimales(self):
        factura = crear_factura_usd(self.cliente, cotizacion=Decimal('1435.123456'))
        _, detalle = self.solicitar(factura)
        self.assertEqual(detalle['MonCotiz'], 1435.123456)

    def test_dolares_sin_cotizacion_valida_no_llama_a_arca(self):
        factura = crear_factura_usd(self.cliente, cotizacion=Decimal('0'))
        resultado, detalle = self.solicitar(factura)
        self.assertFalse(resultado['ok'])
        self.assertIn('cotización', resultado['error'])
        self.assertIsNone(detalle)

    def test_regresion_pesos(self):
        factura = crear_factura(self.cliente, [('2', '150.00', '5'), ('1', '80.00', '4')])
        resultado, detalle = self.solicitar(factura)
        self.assertTrue(resultado['ok'])
        self.assertEqual(detalle['MonId'], 'PES')
        self.assertEqual(detalle['MonCotiz'], 1)
        self.assertNotIn('CanMisMonExt', detalle)
        self.assertEqual(detalle['ImpNeto'], 380.0)
        self.assertEqual(detalle['ImpIVA'], 71.4)
        self.assertEqual(detalle['ImpTotal'], 451.4)

    def test_consultar_cotizacion_de_arca(self):
        from arca import wsfe
        soap = mock.Mock()
        soap.service.FEParamGetCotizacion.return_value = SimpleNamespace(
            Errors=None, ResultGet=SimpleNamespace(MonId='DOL', MonCotiz=1432.5, FchCotiz='20261109'),
        )
        with mock.patch('arca.wsfe.get_client', return_value=soap):
            resultado = wsfe.consultar_cotizacion(
                'token', 'sign', 'DOL', DATOS_ENTORNO, fecha=datetime.date(2026, 11, 9))
        self.assertEqual(resultado, {'ok': True, 'cotizacion': Decimal('1432.5'), 'fecha': '20261109'})
        llamada = soap.service.FEParamGetCotizacion.call_args.kwargs
        self.assertEqual(llamada['MonId'], 'DOL')
        self.assertEqual(llamada['FchCotiz'], '20261109')


@mock.patch('arca.qr.config.CUIT', '20000000001')
class QrMonedaTests(TestCase):
    def datos_qr(self, factura):
        from arca.qr import generar_qr_base64
        with mock.patch('arca.qr.qrcode.make') as make:
            generar_qr_base64(factura)
        url = make.call_args.args[0]
        self.assertTrue(url.startswith('https://www.afip.gob.ar/fe/qr/?p='))
        return json.loads(base64.b64decode(url.split('?p=')[1]))

    def autorizada(self):
        return {
            'estado': 'AUTORIZADA', 'numero': 7, 'cae': '76123456789012',
            'cae_vencimiento': datetime.date(2026, 11, 20),
        }

    def test_qr_en_dolares(self):
        factura = crear_factura_usd(crear_cliente(), **self.autorizada())
        datos = self.datos_qr(factura)
        self.assertEqual(datos['moneda'], 'DOL')
        self.assertEqual(datos['ctz'], 1435.5)
        self.assertEqual(datos['importe'], 121.0)

    def test_regresion_qr_en_pesos(self):
        factura = crear_factura(crear_cliente(), [('1', '100.00', '5')], **self.autorizada())
        datos = self.datos_qr(factura)
        self.assertEqual(datos['moneda'], 'PES')
        self.assertEqual(datos['ctz'], 1)
        self.assertEqual(datos['importe'], 121.0)


# ── PDF ─────────────────────────────────────────────────────────────────────

@mock.patch('reportlab.rl_config.pageCompression', 0)   # texto legible en el PDF
class PdfMonedaTests(TestCase):
    def pdf(self, factura, es_preview=True):
        from arca.pdf_comprobante import generar_pdf
        contenido = generar_pdf(
            factura=factura, empresa=EmpresaConfig.get_config(),
            otros_impuestos=0, qr_b64=None, es_preview=es_preview,
        )
        self.assertTrue(contenido.startswith(b'%PDF'))
        return contenido

    def test_pdf_en_dolares_muestra_moneda_cotizacion_y_equivalente(self):
        factura = crear_factura_usd(crear_cliente(), [('1', '100.00', '5'), ('1', '50.00', '4')])
        contenido = self.pdf(factura)
        self.assertIn(b'Importe Total: US$', contenido)
        self.assertIn(b'IVA 21%: US$', contenido)
        self.assertIn(b'DOL - D', contenido)                      # "DOL - Dólar Estadounidense"
        self.assertIn(b'Tipo de cambio:', contenido)
        self.assertIn(b'$ 1.435,50', contenido)
        self.assertIn(b'Equivalente en pesos:', contenido)
        # Neto 150 / IVA 21 + 5,25 / Total 176,25  ->  × 1435,50
        self.assertIn(b'Total: $ 253.006,88', contenido)
        self.assertIn(b'IVA 21%: $ 30.145,50', contenido)
        self.assertIn(b'IVA 10.5%: $ 7.536,38', contenido)
        self.assertIn(b'asciende a: $ 253.006,88', contenido)

    def test_pdf_factura_b_en_dolares(self):
        factura = crear_factura_usd(crear_cliente(condicion_iva='CF'), tipo_comprobante='6')
        contenido = self.pdf(factura)
        self.assertIn(b'Subtotal IVA: US$', contenido)
        self.assertIn(b'IVA: $ 30.145,50', contenido)
        self.assertIn(b'Total: $ 173.695,50', contenido)

    def test_pdf_autorizado_en_dolares_se_genera(self):
        factura = crear_factura_usd(
            crear_cliente(), estado='AUTORIZADA', numero=7, cae='76123456789012',
            cae_vencimiento=datetime.date(2026, 11, 20),
        )
        self.assertIn(b'CAE N', self.pdf(factura, es_preview=False))

    def test_regresion_pdf_en_pesos(self):
        factura = crear_factura(crear_cliente(), [('1', '100.00', '5')])
        contenido = self.pdf(factura)
        self.assertIn(b'Importe Total: $', contenido)
        self.assertNotIn(b'US$', contenido)
        self.assertNotIn(b'Tipo de cambio', contenido)
        self.assertNotIn(b'Equivalente en pesos', contenido)


# ── Migración sobre datos existentes ────────────────────────────────────────

class MigracionMonedaTests(TransactionTestCase):
    ANTES = [('facturas', '0015_factura_actualizado')]
    DESPUES = [('facturas', '0016_factura_moneda_cotizacion')]

    def tearDown(self):
        # Dejar el esquema al día para el resto de la suite.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_facturas_existentes_quedan_en_pesos_con_cotizacion_1(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.ANTES)
        apps = executor.loader.project_state(self.ANTES).apps
        ClienteViejo = apps.get_model('clientes', 'Cliente')
        FacturaVieja = apps.get_model('facturas', 'Factura')
        ItemViejo = apps.get_model('facturas', 'FacturaItem')
        self.assertFalse(hasattr(FacturaVieja, 'moneda'))

        cliente = ClienteViejo.objects.create(
            nombre_completo='Cliente Histórico', tipo_documento='99',
            numero_documento='', condicion_iva='CF',
        )
        vieja = FacturaVieja.objects.create(
            cliente=cliente, tipo_comprobante='6', punto_venta=3, numero=885,
            estado='AUTORIZADA', cae='75123456789012', entorno_emision='produccion',
        )
        ItemViejo.objects.create(
            factura=vieja, cantidad=1, precio_unitario=Decimal('493300.00'),
            alicuota_iva='5', descripcion_personalizada='Abono',
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.DESPUES)

        factura = Factura.objects.get(pk=vieja.pk)
        self.assertEqual(factura.moneda, 'ARS')
        self.assertEqual(factura.cotizacion, Decimal('1'))
        self.assertEqual(factura.cotizacion_fuente, '')
        self.assertIsNone(factura.cotizacion_fecha)
        self.assertFalse(factura.cancela_misma_moneda)
        # No se perdió nada de lo que ya estaba.
        self.assertEqual(factura.numero, 885)
        self.assertEqual(factura.cae, '75123456789012')
        self.assertEqual(factura.items.count(), 1)
        self.assertEqual(factura.total, 596893.0)
        self.assertEqual(factura.total_en_pesos, factura.total)
        self.assertEqual(factura.simbolo_moneda, '$')
        self.assertEqual(factura.moneda_arca, 'PES')


# ── Servicios con precio en pesos o en dólares ──────────────────────────────

class ServicioMonedaTests(VistasBase):
    def setUp(self):
        super().setUp()
        from servicios.models import Servicio
        self.Servicio = Servicio
        self.en_pesos = Servicio.objects.create(nombre='Abono', precio_unitario=Decimal('157000.00'))
        self.en_dolares = Servicio.objects.create(
            nombre='Pericia', precio_unitario=Decimal('100.00'), moneda='USD', alicuota_iva='4')

    def datos(self, servicio, **params):
        return self.client.get(reverse('datos_servicio', args=[servicio.id]), params).json()

    def test_servicio_existente_queda_en_pesos(self):
        self.assertEqual(self.en_pesos.moneda, 'ARS')
        self.assertEqual(self.en_pesos.simbolo_moneda, '$')
        self.assertEqual(self.en_dolares.simbolo_moneda, 'US$')

    def test_se_puede_editar_la_moneda_del_servicio(self):
        respuesta = self.client.post(reverse('editar_servicio', args=[self.en_pesos.id]), {
            'nombre': 'Abono', 'descripcion': '', 'precio_unitario': '120.00',
            'moneda': 'USD', 'alicuota_iva': '5', 'activo': 'on',
        })
        self.assertEqual(respuesta.status_code, 302)
        self.en_pesos.refresh_from_db()
        self.assertEqual(self.en_pesos.moneda, 'USD')
        self.assertEqual(self.en_pesos.precio_unitario, Decimal('120.00'))

    def test_alta_con_moneda_y_moneda_invalida(self):
        base = {'nombre': 'Nuevo', 'descripcion': '', 'precio_unitario': '50', 'alicuota_iva': '5', 'activo': 'on'}
        self.client.post(reverse('nuevo_servicio'), {**base, 'moneda': 'USD'})
        self.assertEqual(self.Servicio.objects.get(nombre='Nuevo').moneda, 'USD')
        respuesta = self.client.post(reverse('nuevo_servicio'), {**base, 'nombre': 'Otro', 'moneda': 'EUR'})
        self.assertContains(respuesta, 'moneda válida')
        self.assertFalse(self.Servicio.objects.filter(nombre='Otro').exists())

    def test_formulario_y_listado_muestran_la_moneda(self):
        self.assertContains(self.client.get(reverse('nuevo_servicio')), 'name="moneda"')
        respuesta = self.client.get(reverse('listado_servicios'))
        self.assertContains(respuesta, 'US$ 100,00')
        self.assertContains(respuesta, '$ 157.000,00')

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_sin_moneda_devuelve_el_precio_tal_cual(self, get_rate):
        datos = self.datos(self.en_dolares)
        self.assertEqual(datos['precio_unitario'], '100.00')
        self.assertEqual(datos['alicuota_iva'], '4')
        self.assertFalse(datos['convertido'])
        get_rate.assert_not_called()

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_misma_moneda_no_convierte(self, get_rate):
        self.assertEqual(self.datos(self.en_dolares, moneda='USD', cotizacion='1570')['precio_unitario'], '100.00')
        self.assertEqual(self.datos(self.en_pesos, moneda='ARS')['precio_unitario'], '157000.00')
        get_rate.assert_not_called()

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_dolares_a_pesos_usa_la_cotizacion_automatica(self, get_rate):
        get_rate.return_value = cotizacion_falsa('1570')
        datos = self.datos(self.en_dolares, moneda='ARS')
        self.assertEqual(datos['precio_unitario'], '157000.00')
        self.assertTrue(datos['convertido'])
        self.assertEqual(datos['cotizacion'], '1570')
        self.assertEqual(datos['cotizacion_fuente'], 'api:dolarapi')
        self.assertEqual(datos['precio_original'], '100.00')
        self.assertEqual(datos['moneda'], 'USD')

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_pesos_a_dolares_usa_la_cotizacion_elegida_en_la_factura(self, get_rate):
        datos = self.datos(self.en_pesos, moneda='USD', cotizacion='1600,5')
        # 157000 / 1600,5 = 98,0943... -> 98,09
        self.assertEqual(datos['precio_unitario'], '98.09')
        self.assertEqual(datos['cotizacion'], '1600.5')
        self.assertEqual(datos['cotizacion_fuente'], 'factura')
        get_rate.assert_not_called()

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_cotizacion_invalida_cae_en_la_automatica(self, get_rate):
        get_rate.return_value = cotizacion_falsa('1570')
        for valor in ('', '0', '-3', 'abc'):
            datos = self.datos(self.en_pesos, moneda='USD', cotizacion=valor)
            self.assertEqual(datos['precio_unitario'], '100.00', valor)

    @mock.patch('facturas.cotizaciones.get_rate')
    def test_sin_cotizacion_disponible_no_rompe_y_avisa(self, get_rate):
        get_rate.side_effect = cotizaciones.CotizacionNoDisponible('x')
        datos = self.datos(self.en_dolares, moneda='ARS')
        self.assertEqual(datos['precio_unitario'], '100.00')
        self.assertFalse(datos['convertido'])
        self.assertIn('revisalo a mano', datos['aviso'])

    def test_conversion_redondea_half_up(self):
        from .moneda import convertir_precio
        self.assertEqual(convertir_precio('0.005', 'USD', 'ARS', '1'), Decimal('0.01'))
        self.assertEqual(convertir_precio('100', 'ARS', 'USD', '3'), Decimal('33.33'))
        self.assertEqual(convertir_precio('200', 'ARS', 'USD', '3'), Decimal('66.67'))
        self.assertEqual(convertir_precio('10.555', 'ARS', 'ARS', '1570'), Decimal('10.56'))
        with self.assertRaises(ValueError):
            convertir_precio('100', 'ARS', 'USD', '0')


class MigracionServicioMonedaTests(TransactionTestCase):
    ANTES = [('servicios', '0001_initial')]
    DESPUES = [('servicios', '0002_servicio_moneda')]

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_servicios_existentes_quedan_en_pesos(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.ANTES)
        ServicioViejo = executor.loader.project_state(self.ANTES).apps.get_model('servicios', 'Servicio')
        viejo = ServicioViejo.objects.create(nombre='Abono histórico', precio_unitario=Decimal('493300.00'))

        executor = MigrationExecutor(connection)
        executor.migrate(self.DESPUES)

        from servicios.models import Servicio
        servicio = Servicio.objects.get(pk=viejo.pk)
        self.assertEqual(servicio.moneda, 'ARS')
        self.assertEqual(servicio.precio_unitario, Decimal('493300.00'))
