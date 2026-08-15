from django.test import TestCase
from .models import Lead, NotaLead


class LeadModelTests(TestCase):
    def test_estado_por_defecto_es_nuevo(self):
        lead = Lead.objects.create(nombre="Juan Pérez")
        self.assertEqual(lead.estado, 'NUEVO')

    def test_str_devuelve_nombre(self):
        lead = Lead.objects.create(nombre="Juan Pérez")
        self.assertEqual(str(lead), "Juan Pérez")

    def test_esta_ganado_false_por_defecto(self):
        lead = Lead.objects.create(nombre="Juan Pérez")
        self.assertFalse(lead.esta_ganado)

    def test_esta_ganado_true_cuando_estado_ganado(self):
        lead = Lead.objects.create(nombre="Juan Pérez", estado='GANADO')
        self.assertTrue(lead.esta_ganado)


class NotaLeadModelTests(TestCase):
    def test_nota_queda_asociada_al_lead(self):
        lead = Lead.objects.create(nombre="Juan Pérez")
        nota = NotaLead.objects.create(lead=lead, texto="Llamó preguntando precios.")
        self.assertEqual(lead.notas.count(), 1)
        self.assertEqual(lead.notas.first(), nota)


from django.contrib.auth.models import User
from django.urls import reverse


class KanbanViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='pass12345')
        self.client.force_login(self.user)

    def test_requiere_login(self):
        self.client.logout()
        response = self.client.get(reverse('kanban_leads'))
        self.assertEqual(response.status_code, 302)

    def test_muestra_las_cinco_columnas(self):
        response = self.client.get(reverse('kanban_leads'))
        self.assertEqual(response.status_code, 200)
        for _, etiqueta in Lead.ESTADOS:
            self.assertContains(response, etiqueta)

    def test_lead_aparece_en_su_columna(self):
        Lead.objects.create(nombre="Ana Gómez", estado='CONTACTADO')
        response = self.client.get(reverse('kanban_leads'))
        self.assertContains(response, "Ana Gómez")


class NuevoLeadViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester2', password='pass12345')
        self.client.force_login(self.user)

    def test_crear_lead_valido_redirige_al_detalle(self):
        response = self.client.post(reverse('nuevo_lead'), {
            'nombre': 'Marcos Ruiz', 'telefono': '1122334455', 'email': '',
            'origen': 'REFERIDO', 'proximo_contacto': '',
        })
        lead = Lead.objects.get(nombre='Marcos Ruiz')
        self.assertRedirects(response, reverse('detalle_lead', args=[lead.id]))
        self.assertEqual(lead.origen, 'REFERIDO')

    def test_crear_lead_sin_nombre_muestra_error(self):
        response = self.client.post(reverse('nuevo_lead'), {'nombre': '', 'origen': 'OTRO'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "necesita un nombre")
        self.assertEqual(Lead.objects.count(), 0)


class DetalleLeadViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester3', password='pass12345')
        self.client.force_login(self.user)
        self.lead = Lead.objects.create(nombre="Lucía Fernández")

    def test_detalle_muestra_nombre(self):
        response = self.client.get(reverse('detalle_lead', args=[self.lead.id]))
        self.assertContains(response, "Lucía Fernández")

    def test_agregar_nota(self):
        response = self.client.post(
            reverse('agregar_nota_lead', args=[self.lead.id]),
            {'texto': 'Pidió una demo para el jueves.'},
        )
        self.assertRedirects(response, reverse('detalle_lead', args=[self.lead.id]))
        self.assertEqual(self.lead.notas.count(), 1)
        self.assertEqual(self.lead.notas.first().texto, 'Pidió una demo para el jueves.')

    def test_agregar_nota_vacia_no_guarda_nada(self):
        self.client.post(reverse('agregar_nota_lead', args=[self.lead.id]), {'texto': '  '})
        self.assertEqual(self.lead.notas.count(), 0)


class ActualizarEstadoLeadViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester4', password='pass12345')
        self.client.force_login(self.user)
        self.lead = Lead.objects.create(nombre="Pedro Sosa", estado='NUEVO')

    def test_mover_a_contactado(self):
        response = self.client.post(
            reverse('actualizar_estado_lead', args=[self.lead.id]), {'estado': 'CONTACTADO'}
        )
        self.assertEqual(response.status_code, 204)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.estado, 'CONTACTADO')

    def test_estado_invalido_devuelve_400(self):
        response = self.client.post(
            reverse('actualizar_estado_lead', args=[self.lead.id]), {'estado': 'NO_EXISTE'}
        )
        self.assertEqual(response.status_code, 400)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.estado, 'NUEVO')

    def test_no_permite_mover_directo_a_ganado(self):
        """GANADO solo se alcanza vía convertir_lead (Task 5), no arrastrando la tarjeta."""
        response = self.client.post(
            reverse('actualizar_estado_lead', args=[self.lead.id]), {'estado': 'GANADO'}
        )
        self.assertEqual(response.status_code, 400)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.estado, 'NUEVO')

    def test_get_no_permitido(self):
        response = self.client.get(reverse('actualizar_estado_lead', args=[self.lead.id]))
        self.assertEqual(response.status_code, 405)


from clientes.models import Cliente


class ConvertirLeadViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester5', password='pass12345')
        self.client.force_login(self.user)
        self.lead = Lead.objects.create(nombre="Carla Díaz", telefono="1155667788")

    def test_form_precarga_nombre_del_lead(self):
        response = self.client.get(reverse('convertir_lead', args=[self.lead.id]))
        self.assertContains(response, "Carla Díaz")

    def test_convertir_lead_crea_cliente_y_marca_ganado(self):
        response = self.client.post(reverse('convertir_lead', args=[self.lead.id]), {
            'nombre_completo': 'Carla Díaz', 'tipo_documento': '96',
            'numero_documento': '30111222', 'condicion_iva': 'CF',
            'telefono': '1155667788', 'email': '', 'direccion': '',
        })
        self.lead.refresh_from_db()
        self.assertTrue(self.lead.esta_ganado)
        self.assertIsNotNone(self.lead.cliente_id)
        cliente = Cliente.objects.get(numero_documento='30111222')
        self.assertEqual(self.lead.cliente_id, cliente.id)
        self.assertRedirects(response, reverse('ficha_cliente_crm', args=[cliente.id]))

    def test_convertir_sin_numero_documento_muestra_error(self):
        response = self.client.post(reverse('convertir_lead', args=[self.lead.id]), {
            'nombre_completo': 'Carla Díaz', 'tipo_documento': '96',
            'numero_documento': '', 'condicion_iva': 'CF',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "número de documento")
        self.lead.refresh_from_db()
        self.assertFalse(self.lead.esta_ganado)

    def test_lead_ya_convertido_redirige_directo_a_la_ficha(self):
        cliente = Cliente.objects.create(
            nombre_completo='Carla Díaz', tipo_documento='96',
            numero_documento='30111222', condicion_iva='CF',
        )
        self.lead.cliente = cliente
        self.lead.estado = 'GANADO'
        self.lead.save(update_fields=['cliente', 'estado', 'actualizado'])

        response = self.client.get(reverse('convertir_lead', args=[self.lead.id]))
        self.assertRedirects(response, reverse('ficha_cliente_crm', args=[cliente.id]))


from datetime import date
from facturas.models import Factura, FacturaItem
from servicios.models import Servicio
from tickets.models import Ticket


class FichaClienteViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester6', password='pass12345')
        self.client.force_login(self.user)
        self.cliente = Cliente.objects.create(
            nombre_completo='Empresa Test', tipo_documento='80',
            numero_documento='20111222339', condicion_iva='RI',
        )

    def test_muestra_datos_del_cliente(self):
        response = self.client.get(reverse('ficha_cliente_crm', args=[self.cliente.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Empresa Test')

    def test_timeline_incluye_factura_y_ticket(self):
        servicio = Servicio.objects.create(nombre='Consulta', precio_unitario=1000)
        factura = Factura.objects.create(cliente=self.cliente, tipo_comprobante='6')
        FacturaItem.objects.create(
            factura=factura, servicio=servicio, cantidad=1,
            precio_unitario=1000, alicuota_iva='5',
        )
        ticket = Ticket.objects.create(
            cliente=self.cliente, titulo='No anda el login', descripcion='Detalle del problema.',
        )

        response = self.client.get(reverse('ficha_cliente_crm', args=[self.cliente.id]))
        self.assertContains(response, factura.letra_comprobante)
        self.assertContains(response, ticket.titulo)

    def test_muestra_notas_del_lead_ganado(self):
        lead = Lead.objects.create(nombre='Empresa Test', estado='GANADO', cliente=self.cliente)
        NotaLead.objects.create(lead=lead, texto='Cliente muy puntual con los pagos.')

        response = self.client.get(reverse('ficha_cliente_crm', args=[self.cliente.id]))
        self.assertContains(response, 'Cliente muy puntual con los pagos.')

    def test_convertir_lead_redirige_ahora_correctamente(self):
        """Cierra el forward-reference de Task 5: la conversión ahora redirige a una URL real."""
        lead = Lead.objects.create(nombre='Otra Empresa')
        response = self.client.post(reverse('convertir_lead', args=[lead.id]), {
            'nombre_completo': 'Otra Empresa', 'tipo_documento': '96',
            'numero_documento': '30999888', 'condicion_iva': 'CF',
            'telefono': '', 'email': '', 'direccion': '',
        })
        cliente = Cliente.objects.get(numero_documento='30999888')
        self.assertRedirects(response, reverse('ficha_cliente_crm', args=[cliente.id]))
