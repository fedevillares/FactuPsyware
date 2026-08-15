from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Cliente


class ListadoClientesFichaLinkTests(TestCase):
    """El nombre del cliente en el listado debe llevar a la ficha 360 del
    CRM, no al formulario de edición (edición queda en el ícono de lápiz)."""

    def setUp(self):
        self.user = User.objects.create_user('tester_clientes', password='clave-de-test')
        self.client.force_login(self.user)
        self.cliente = Cliente.objects.create(
            nombre_completo='Cliente UI Test', tipo_documento='96',
            numero_documento='30999111', condicion_iva='CF',
        )

    def test_nombre_enlaza_a_ficha_360(self):
        respuesta = self.client.get(reverse('listado_clientes'))
        self.assertContains(
            respuesta,
            f'href="{reverse("ficha_cliente_crm", args=[self.cliente.id])}" style="font-weight:500;">{self.cliente.nombre_completo}',
        )

    def test_boton_eliminar_deshabilitado_es_focuseable(self):
        from facturas.models import Factura
        Factura.objects.create(cliente=self.cliente, tipo_comprobante='6', punto_venta=1)
        respuesta = self.client.get(reverse('listado_clientes'))
        self.assertContains(respuesta, '<button type="button" class="btn btn-outline btn-icon" style="opacity:.4; cursor:not-allowed;" disabled')
