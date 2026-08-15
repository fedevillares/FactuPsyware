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


class EditarLeadViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester7', password='pass12345')
        self.client.force_login(self.user)
        self.lead = Lead.objects.create(nombre="Roberto Paz", telefono="1100000000", origen='WEB')

    def test_form_precarga_datos_actuales(self):
        response = self.client.get(reverse('editar_lead', args=[self.lead.id]))
        self.assertContains(response, "Roberto Paz")
        self.assertContains(response, "1100000000")

    def test_editar_lead_guarda_cambios(self):
        response = self.client.post(reverse('editar_lead', args=[self.lead.id]), {
            'nombre': 'Roberto Paz Actualizado', 'telefono': '1199999999',
            'email': 'roberto@example.com', 'origen': 'REFERIDO',
            'proximo_contacto': '2026-09-01',
        })
        self.assertRedirects(response, reverse('detalle_lead', args=[self.lead.id]))
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.nombre, 'Roberto Paz Actualizado')
        self.assertEqual(self.lead.telefono, '1199999999')
        self.assertEqual(self.lead.origen, 'REFERIDO')

    def test_editar_no_modifica_estado_ni_cliente(self):
        self.lead.estado = 'CONTACTADO'
        self.lead.save(update_fields=['estado', 'actualizado'])
        self.client.post(reverse('editar_lead', args=[self.lead.id]), {
            'nombre': 'Roberto Paz', 'telefono': '', 'email': '', 'origen': 'OTRO',
            'proximo_contacto': '',
        })
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.estado, 'CONTACTADO')
        self.assertIsNone(self.lead.cliente_id)

    def test_editar_sin_nombre_muestra_error(self):
        response = self.client.post(reverse('editar_lead', args=[self.lead.id]), {'nombre': '', 'origen': 'OTRO'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "necesita un nombre")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.nombre, "Roberto Paz")


from datetime import timedelta
from .models import Actividad


class ActividadModelTests(TestCase):
    def setUp(self):
        self.lead = Lead.objects.create(nombre="Marta Ibáñez")

    def test_defaults(self):
        actividad = Actividad.objects.create(
            lead=self.lead, titulo="Llamar para confirmar", fecha=date.today(),
        )
        self.assertEqual(actividad.tipo, 'NOTA')
        self.assertFalse(actividad.hecha)
        self.assertFalse(actividad.recordatorio_enviado)

    def test_esta_vencida_true_si_no_hecha_y_fecha_pasada(self):
        actividad = Actividad.objects.create(
            lead=self.lead, titulo="Llamar", fecha=date.today() - timedelta(days=1),
        )
        self.assertTrue(actividad.esta_vencida)

    def test_esta_vencida_false_si_hecha(self):
        actividad = Actividad.objects.create(
            lead=self.lead, titulo="Llamar", fecha=date.today() - timedelta(days=1), hecha=True,
        )
        self.assertFalse(actividad.esta_vencida)

    def test_esta_vencida_false_si_fecha_futura(self):
        actividad = Actividad.objects.create(
            lead=self.lead, titulo="Llamar", fecha=date.today() + timedelta(days=1),
        )
        self.assertFalse(actividad.esta_vencida)

    def test_relacion_inversa_desde_lead(self):
        Actividad.objects.create(lead=self.lead, titulo="Llamar", fecha=date.today())
        self.assertEqual(self.lead.actividades.count(), 1)


class AgregarActividadLeadViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester8', password='pass12345')
        self.client.force_login(self.user)
        self.lead = Lead.objects.create(nombre="Marta Ibáñez")

    def test_agregar_actividad(self):
        response = self.client.post(reverse('agregar_actividad_lead', args=[self.lead.id]), {
            'tipo': 'LLAMADA', 'titulo': 'Llamar para confirmar', 'fecha': '2026-09-01',
        })
        self.assertRedirects(response, reverse('detalle_lead', args=[self.lead.id]))
        self.assertEqual(self.lead.actividades.count(), 1)
        actividad = self.lead.actividades.first()
        self.assertEqual(actividad.tipo, 'LLAMADA')
        self.assertEqual(actividad.titulo, 'Llamar para confirmar')

    def test_agregar_actividad_hecha(self):
        self.client.post(reverse('agregar_actividad_lead', args=[self.lead.id]), {
            'tipo': 'NOTA', 'titulo': 'Ya llamé', 'fecha': '2026-08-01', 'hecha': 'on',
        })
        self.assertTrue(self.lead.actividades.first().hecha)

    def test_agregar_actividad_sin_titulo_no_guarda(self):
        self.client.post(reverse('agregar_actividad_lead', args=[self.lead.id]), {
            'tipo': 'NOTA', 'titulo': '', 'fecha': '2026-09-01',
        })
        self.assertEqual(self.lead.actividades.count(), 0)

    def test_agregar_actividad_sin_fecha_no_guarda(self):
        self.client.post(reverse('agregar_actividad_lead', args=[self.lead.id]), {
            'tipo': 'NOTA', 'titulo': 'Algo', 'fecha': '',
        })
        self.assertEqual(self.lead.actividades.count(), 0)


class MarcarActividadHechaViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester9', password='pass12345')
        self.client.force_login(self.user)
        self.lead = Lead.objects.create(nombre="Marta Ibáñez")
        self.actividad = Actividad.objects.create(lead=self.lead, titulo="Llamar", fecha=date.today())

    def test_marcar_hecha(self):
        response = self.client.post(reverse('marcar_actividad_hecha', args=[self.actividad.id]))
        self.assertRedirects(response, reverse('detalle_lead', args=[self.lead.id]))
        self.actividad.refresh_from_db()
        self.assertTrue(self.actividad.hecha)

    def test_get_no_permitido(self):
        response = self.client.get(reverse('marcar_actividad_hecha', args=[self.actividad.id]))
        self.assertEqual(response.status_code, 405)


from unittest.mock import patch
from crm.recordatorios import enviar_recordatorios_vencidos


class RecordatoriosTests(TestCase):
    def test_sin_email_configurado_no_hace_nada(self):
        """EmpresaConfig por defecto no tiene email configurado (test DB limpia),
        así que esto no debe intentar ninguna conexión de red."""
        lead = Lead.objects.create(nombre="Marta Ibáñez")
        Actividad.objects.create(lead=lead, titulo="Llamar", fecha=date.today() - timedelta(days=1))
        enviar_recordatorios_vencidos()
        actividad = lead.actividades.first()
        self.assertFalse(actividad.recordatorio_enviado)

    def test_no_toca_actividades_no_vencidas(self):
        lead = Lead.objects.create(nombre="Marta Ibáñez")
        Actividad.objects.create(lead=lead, titulo="Llamar", fecha=date.today() + timedelta(days=5))
        enviar_recordatorios_vencidos()
        self.assertFalse(lead.actividades.first().recordatorio_enviado)

    @patch('crm.recordatorios.empresa_tiene_email_configurado', return_value=True)
    @patch('crm.recordatorios.conexion_smtp')
    def test_marca_enviado_aunque_falle_el_envio(self, mock_conexion, mock_configurado):
        lead = Lead.objects.create(nombre="Marta Ibáñez")
        actividad = Actividad.objects.create(lead=lead, titulo="Llamar", fecha=date.today() - timedelta(days=1))
        with patch('crm.recordatorios.EmailMessage') as mock_email_cls:
            mock_email_cls.return_value.send.side_effect = Exception("fallo de red simulado")
            enviar_recordatorios_vencidos()
        actividad.refresh_from_db()
        self.assertTrue(actividad.recordatorio_enviado)


class CrmDashboardViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester10', password='pass12345')
        self.client.force_login(self.user)

    def test_requiere_login(self):
        self.client.logout()
        response = self.client.get(reverse('crm_dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_muestra_leads_activos(self):
        Lead.objects.create(nombre="Nuevo Lead", estado='NUEVO')
        Lead.objects.create(nombre="Lead Ganado", estado='GANADO')
        response = self.client.get(reverse('crm_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nuevo Lead")

    def test_tasa_conversion_cero_sin_datos(self):
        response = self.client.get(reverse('crm_dashboard'))
        self.assertContains(response, "0")

    def test_muestra_actividad_vencida(self):
        lead = Lead.objects.create(nombre="Con actividad vencida")
        Actividad.objects.create(lead=lead, titulo="Llamar urgente", fecha=date.today() - timedelta(days=2))
        response = self.client.get(reverse('crm_dashboard'))
        self.assertContains(response, "Llamar urgente")

    def test_muestra_top_clientes_por_facturacion(self):
        cliente = Cliente.objects.create(
            nombre_completo='Empresa Top', tipo_documento='80',
            numero_documento='20333444555', condicion_iva='RI',
        )
        servicio = Servicio.objects.create(nombre='Consulta', precio_unitario=5000)
        factura = Factura.objects.create(cliente=cliente, tipo_comprobante='6', estado='AUTORIZADA')
        FacturaItem.objects.create(factura=factura, servicio=servicio, cantidad=1, precio_unitario=5000, alicuota_iva='5')

        response = self.client.get(reverse('crm_dashboard'))
        self.assertContains(response, "Empresa Top")

    def test_pipeline_sigue_andando_en_su_nueva_ruta(self):
        response = self.client.get(reverse('kanban_leads'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request['PATH_INFO'], '/crm/pipeline/')


class FichaClienteEnriquecidaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester11', password='pass12345')
        self.client.force_login(self.user)
        self.cliente = Cliente.objects.create(
            nombre_completo='Empresa Rica', tipo_documento='80',
            numero_documento='20444555666', condicion_iva='RI',
        )
        self.servicio = Servicio.objects.create(nombre='Consulta', precio_unitario=2000)

    def test_muestra_total_facturado_solo_autorizadas(self):
        autorizada = Factura.objects.create(cliente=self.cliente, tipo_comprobante='6', estado='AUTORIZADA')
        FacturaItem.objects.create(factura=autorizada, servicio=self.servicio, cantidad=1, precio_unitario=2000, alicuota_iva='8')
        Factura.objects.create(cliente=self.cliente, tipo_comprobante='6', estado='BORRADOR')

        response = self.client.get(reverse('ficha_cliente_crm', args=[self.cliente.id]))
        self.assertContains(response, "2.100")  # 2000 + 5% IVA = 2100, con separador de miles

    def test_muestra_tickets_abiertos(self):
        Ticket.objects.create(cliente=self.cliente, titulo="Ticket abierto", descripcion="Detalle", estado='PENDIENTE')
        Ticket.objects.create(cliente=self.cliente, titulo="Ticket cerrado", descripcion="Detalle", estado='CERRADO')

        response = self.client.get(reverse('ficha_cliente_crm', args=[self.cliente.id]))
        self.assertContains(response, "1")  # 1 ticket abierto en el stat-card

    def test_sin_facturas_no_rompe(self):
        response = self.client.get(reverse('ficha_cliente_crm', args=[self.cliente.id]))
        self.assertEqual(response.status_code, 200)
