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
