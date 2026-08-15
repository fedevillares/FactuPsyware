"""
Tests de las barreras de seguridad del panel de backup/restauración.

No tocan la base de datos real: la vista de importación se corta en las
validaciones (confirmación, extensión, magic bytes) antes de escribir nada.
"""
import io

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from arca.admin import EmpresaConfigForm
from arca.crypto import cifrar, descifrar
from arca.models import EmpresaConfig


def archivo_sqlite_falso(nombre='backup_test.sqlite3', contenido=b'SQLite format 3\x00' + b'\x00' * 100):
    return SimpleUploadedFile(nombre, contenido, content_type='application/octet-stream')


class ImportarDbGuardasTests(TestCase):
    """La restauración de la base exige confirmación explícita del servidor."""

    def setUp(self):
        self.user = User.objects.create_user('tester', password='clave-de-test')
        self.client.force_login(self.user)
        self.url = reverse('importar_db')

    def test_sin_login_redirige(self):
        self.client.logout()
        respuesta = self.client.post(self.url, {})
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('/accounts/login/', respuesta['Location'])

    def test_get_no_permitido(self):
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 405)

    def test_sin_confirmacion_rechazado(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(),
        }, follow=True)
        self.assertContains(respuesta, 'RESTAURAR')

    def test_confirmacion_incorrecta_rechazada(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(),
            'confirmacion': 'restaurar ya',
        }, follow=True)
        self.assertContains(respuesta, 'RESTAURAR')

    def test_extension_invalida_rechazada(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(nombre='cualquiercosa.txt'),
            'confirmacion': 'RESTAURAR',
        }, follow=True)
        self.assertContains(respuesta, '.sqlite3')

    def test_contenido_no_sqlite_rechazado(self):
        respuesta = self.client.post(self.url, {
            'archivo_db': archivo_sqlite_falso(contenido=b'no soy una base de datos'),
            'confirmacion': 'RESTAURAR',
        }, follow=True)
        self.assertContains(respuesta, 'no es una base de datos SQLite')


class EliminarBackupGuardasTests(TestCase):
    """El borrado de backups no debe permitir path traversal."""

    def setUp(self):
        self.user = User.objects.create_user('tester', password='clave-de-test')
        self.client.force_login(self.user)
        self.url = reverse('eliminar_backup')

    def test_nombre_con_ruta_rechazado(self):
        for nombre in ['../db.sqlite3', 'backup_../../db.sqlite3', 'db.sqlite3', '']:
            respuesta = self.client.post(self.url, {'nombre': nombre}, follow=True)
            # Nunca debe reportar éxito de borrado para nombres inválidos
            self.assertNotContains(respuesta, 'eliminado')


class CifradoPasswordTests(TestCase):
    def test_roundtrip(self):
        self.assertEqual(descifrar(cifrar('mi-clave-secreta')), 'mi-clave-secreta')

    def test_cifrar_vacio_devuelve_vacio(self):
        self.assertEqual(cifrar(''), '')
        self.assertEqual(cifrar(None), '')

    def test_descifrar_vacio_devuelve_vacio(self):
        self.assertEqual(descifrar(''), '')
        self.assertEqual(descifrar(None), '')

    def test_descifrar_valor_invalido_devuelve_vacio(self):
        self.assertEqual(descifrar('esto-no-es-un-token-valido'), '')

    def test_dos_cifrados_del_mismo_texto_son_distintos(self):
        # Fernet incluye un IV aleatorio: no debe ser determinista.
        self.assertNotEqual(cifrar('hola'), cifrar('hola'))


class EmpresaConfigEmailPasswordTests(TestCase):
    def test_email_password_plano_descifra(self):
        empresa = EmpresaConfig.get_config()
        empresa.email_password = cifrar('appsecret123')
        empresa.save(update_fields=['email_password'])
        self.assertEqual(empresa.email_password_plano, 'appsecret123')

    def test_email_password_plano_vacio_si_no_hay_password(self):
        empresa = EmpresaConfig.get_config()
        empresa.email_password = ''
        empresa.save(update_fields=['email_password'])
        self.assertEqual(empresa.email_password_plano, '')


class EmpresaConfigFormPasswordTests(TestCase):
    def _datos_minimos(self, **overrides):
        datos = {
            'razon_social': 'Test SRL', 'cuit': '20111222339',
            'condicion_iva': 'IVA Responsable Inscripto',
            'domicilio': 'Calle Falsa 123', 'localidad': 'CABA',
            'punto_venta_defecto': 1, 'otros_impuestos_pct': '0',
        }
        datos.update(overrides)
        return datos

    def test_dejar_en_blanco_preserva_password_existente(self):
        empresa = EmpresaConfig.get_config()
        empresa.email_password = cifrar('claveOriginal')
        empresa.save(update_fields=['email_password'])

        form = EmpresaConfigForm(data=self._datos_minimos(email_password=''), instance=empresa)
        self.assertTrue(form.is_valid(), form.errors)
        guardado = form.save()
        self.assertEqual(guardado.email_password_plano, 'claveOriginal')

    def test_escribir_nueva_password_la_cifra(self):
        empresa = EmpresaConfig.get_config()
        form = EmpresaConfigForm(data=self._datos_minimos(email_password='claveNueva'), instance=empresa)
        self.assertTrue(form.is_valid(), form.errors)
        guardado = form.save()
        self.assertEqual(guardado.email_password_plano, 'claveNueva')
        self.assertNotEqual(guardado.email_password, 'claveNueva')
